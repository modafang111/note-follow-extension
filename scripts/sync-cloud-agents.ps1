#Requires -Version 5.1
<#
.SYNOPSIS
  Cursor Cloud Agent が push したブランチを、手元の git worktree に一括で取り込む。

.DESCRIPTION
  Git リポジトリではない場所からでも実行できる。
  リポジトリが無ければ D:\dev\note-follow-extension にクローンし、今のブランチは切り替えない。

  会話履歴の「Move to Local」は API に無いので、このスクリプトはコードだけ同期する。

.EXAMPLE
  $env:CURSOR_API_KEY = "key_xxxxxxxx"
  powershell -ExecutionPolicy Bypass -File D:\dev\note-follow-extension\scripts\sync-cloud-agents.ps1
#>
[CmdletBinding()]
param(
    [string]$RepoPath,
    [string]$RepoUrl = "https://github.com/modafang111/note-follow-extension.git",
    [string]$DevRoot,
    [string]$WorktreeRoot,
    [switch]$ListOnly,
    [switch]$NoClone
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ApiBase = if ($env:CURSOR_API_BASE) { $env:CURSOR_API_BASE.TrimEnd("/") } else { "https://api.cursor.com" }
if (-not $DevRoot) {
    if ($env:CURSOR_SYNC_ROOT) { $DevRoot = $env:CURSOR_SYNC_ROOT } else { $DevRoot = "D:\dev" }
}
$DefaultClonePath = Join-Path $DevRoot "note-follow-extension"

function Write-Info([string]$Message) { Write-Host $Message }
function Write-WarnLine([string]$Message) { Write-Host "skip  $Message" -ForegroundColor Yellow }
function Write-Fail([string]$Message) { Write-Host "error $Message" -ForegroundColor Red }

function Get-GitExe {
    $cmd = Get-Command git -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "C:\Program Files\Git\cmd\git.exe",
        "C:\Program Files (x86)\Git\cmd\git.exe"
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }
    return $null
}

function Invoke-Git {
    param([Parameter(Mandatory)][string[]]$GitArgs, [string]$WorkDir)
    $git = Get-GitExe
    if (-not $git) {
        throw "git が見つかりません。Git for Windows を PATH に入れてください。"
    }
    if ($WorkDir) {
        & $git -C $WorkDir @GitArgs
    } else {
        & $git @GitArgs
    }
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') が終了コード $LASTEXITCODE で失敗しました。"
    }
}

function Test-GitRepo([string]$Path) {
    if (-not (Test-Path $Path)) { return $false }
    $git = Get-GitExe
    if (-not $git) { return $false }
    & $git -C $Path rev-parse --is-inside-work-tree 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Get-CursorAuthHeader {
    $key = $env:CURSOR_API_KEY
    if ([string]::IsNullOrWhiteSpace($key)) {
        Write-Fail "CURSOR_API_KEY が未設定です。チャットにキーを貼らないでください。"
        Write-Info ""
        Write-Info "キーの発行: https://cursor.com/dashboard/api"
        Write-Info "同じ PowerShell セッションで:"
        Write-Info '  $env:CURSOR_API_KEY = "（発行したキー）"'
        Write-Info "永続化するなら（ユーザー環境変数）:"
        Write-Info '  [System.Environment]::SetEnvironmentVariable("CURSOR_API_KEY", "（発行したキー）", "User")'
        Write-Info "設定後、このスクリプトをもう一度実行してください。"
        exit 2
    }
    $bytes = [Text.Encoding]::ASCII.GetBytes("${key}:")
    $b64 = [Convert]::ToBase64String($bytes)
    return @{ Authorization = "Basic $b64" }
}

function Invoke-CursorApi([string]$Path) {
    $url = "$ApiBase$Path"
    try {
        return Invoke-RestMethod -Method Get -Uri $url -Headers (Get-CursorAuthHeader)
    } catch {
        $code = $null
        if ($_.Exception.Response) {
            $code = [int]$_.Exception.Response.StatusCode
        }
        if ($code -eq 401 -or $code -eq 403) {
            throw "Cursor API がキーを拒否しました (HTTP $code)。CURSOR_API_KEY を再発行して入れ直してください。"
        }
        throw "Cursor API 呼び出しに失敗しました: $url`n$($_.Exception.Message)"
    }
}

function ConvertTo-RepoSlug([string]$Url) {
    if ([string]::IsNullOrWhiteSpace($Url)) { return "" }
    $slug = $Url.Trim()
    $slug = $slug -replace '^https?://', ''
    $slug = $slug -replace '\.git$', ''
    $slug = $slug.TrimEnd('/')
    return $slug.ToLowerInvariant()
}

function Get-AgentItems {
    $items = New-Object System.Collections.Generic.List[object]
    $cursor = $null
    do {
        $qs = "limit=100&includeArchived=false"
        if ($cursor) { $qs += "&cursor=$([uri]::EscapeDataString($cursor))" }
        $page = Invoke-CursorApi "/v1/agents?$qs"
        $batch = @()
        $names = @($page.PSObject.Properties.Name)
        if ($names -contains "items" -and $null -ne $page.items) { $batch = @($page.items) }
        elseif ($names -contains "agents" -and $null -ne $page.agents) { $batch = @($page.agents) }
        foreach ($item in $batch) { $items.Add($item) }
        $cursor = $null
        if ($page.PSObject.Properties.Name -contains "nextCursor" -and $page.nextCursor) {
            $cursor = $page.nextCursor
        }
    } while ($cursor)
    return $items
}

function Get-AgentBranches($AgentSummary) {
    $branches = @()
    $latestRunId = $null
    if (@($AgentSummary.PSObject.Properties.Name) -contains "latestRunId") {
        $latestRunId = $AgentSummary.latestRunId
    }
    if (-not $latestRunId) {
        $detail = Invoke-CursorApi "/v1/agents/$($AgentSummary.id)"
        if (@($detail.PSObject.Properties.Name) -contains "latestRunId") {
            $latestRunId = $detail.latestRunId
        }
    }
    if (-not $latestRunId) { return $branches }
    $run = Invoke-CursorApi "/v1/agents/$($AgentSummary.id)/runs/$latestRunId"
    if (
        (@($run.PSObject.Properties.Name) -contains "git") -and
        $null -ne $run.git -and
        (@($run.git.PSObject.Properties.Name) -contains "branches") -and
        $null -ne $run.git.branches
    ) {
        $branches = @($run.git.branches)
    }
    return $branches
}

function Resolve-RepoPath {
    if ($RepoPath) {
        if (-not (Test-GitRepo $RepoPath)) {
            throw "RepoPath が Git リポジトリではありません: $RepoPath"
        }
        return (Resolve-Path $RepoPath).Path
    }

    if (Test-GitRepo $DefaultClonePath) {
        return (Resolve-Path $DefaultClonePath).Path
    }

    if (Test-GitRepo (Get-Location).Path) {
        $top = Invoke-Git -GitArgs @("rev-parse", "--show-toplevel")
        return $top.Trim()
    }

    if ($NoClone) {
        throw "Git リポジトリが見つかりません。-RepoPath を指定するか、先にクローンしてください。"
    }

    Write-Info "リポジトリが無いのでクローンします: $RepoUrl"
    Write-Info "  -> $DefaultClonePath"
    $parent = Split-Path $DefaultClonePath -Parent
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent | Out-Null
    }
    Invoke-Git -GitArgs @("clone", $RepoUrl, $DefaultClonePath)
    return $DefaultClonePath
}

if (-not (Get-GitExe)) {
    Write-Fail "git が見つかりません。Git for Windows をインストールし、新しい PowerShell を開き直してください。"
    Write-Info "  https://git-scm.com/download/win"
    exit 1
}

$headersProbe = Get-CursorAuthHeader
[void]$headersProbe

$resolvedRepo = Resolve-RepoPath
$targetSlug = ConvertTo-RepoSlug $RepoUrl
$originUrl = (Invoke-Git -WorkDir $resolvedRepo -GitArgs @("remote", "get-url", "origin")).Trim()
$originSlug = ConvertTo-RepoSlug $originUrl

if ($WorktreeRoot) {
    $wtRoot = $WorktreeRoot
} else {
    $wtRoot = Join-Path $DevRoot "cursor-cloud-worktrees\note-follow-extension"
}
New-Item -ItemType Directory -Force -Path $wtRoot | Out-Null

Write-Info "repo     $resolvedRepo"
Write-Info "origin   $originUrl"
Write-Info "worktrees $wtRoot"
Write-Info "fetch しています..."
Invoke-Git -WorkDir $resolvedRepo -GitArgs @("fetch", "origin", "--prune") | Out-Null

$agents = @(Get-AgentItems)
Write-Info ("cloud agents: {0} 件" -f $agents.Count)

$ok = 0
$skipped = 0
$failed = 0
$seen = @{}

foreach ($agent in $agents) {
    $name = $agent.name
    if (-not $name) { $name = $agent.id }
    try {
        $branchInfos = @(Get-AgentBranches $agent)
    } catch {
        Write-WarnLine "$name  (run 取得失敗: $($_.Exception.Message))"
        $failed++
        continue
    }

    $matched = @($branchInfos | Where-Object {
        $slug = ConvertTo-RepoSlug $_.repoUrl
        (-not $slug) -or ($slug -eq $targetSlug) -or ($slug -eq $originSlug)
    })

    if ($matched.Count -eq 0) {
        Write-WarnLine "$name  (このリポジトリへの push ブランチがまだ無い)"
        $skipped++
        continue
    }

    foreach ($info in $matched) {
        $branch = $info.branch
        if ([string]::IsNullOrWhiteSpace($branch)) { continue }
        if ($seen.ContainsKey($branch)) { continue }
        $seen[$branch] = $true

        $safe = ($branch -replace '[\\/:*?"<>|]', "-")
        $dest = Join-Path $wtRoot $safe
        $pr = $info.prUrl
        $prNote = if ($pr) { "  PR $pr" } else { "" }

        if ($ListOnly) {
            Write-Info "list  $branch$prNote"
            $ok++
            continue
        }

        $remoteRef = "refs/remotes/origin/$branch"
        $hasRemote = $true
        try {
            Invoke-Git -WorkDir $resolvedRepo -GitArgs @("show-ref", "--verify", "--quiet", $remoteRef)
        } catch {
            $hasRemote = $false
        }
        if (-not $hasRemote) {
            Write-WarnLine "$branch  (origin にまだ無い)$prNote"
            $skipped++
            continue
        }

        if (Test-Path $dest) {
            try {
                Invoke-Git -WorkDir $dest -GitArgs @("fetch", "origin", $branch)
                Invoke-Git -WorkDir $dest -GitArgs @("checkout", $branch)
                Invoke-Git -WorkDir $dest -GitArgs @("pull", "--ff-only")
                Write-Info "upd   $branch -> $dest$prNote"
                $ok++
            } catch {
                Write-WarnLine "$branch  (更新失敗: $($_.Exception.Message))"
                $failed++
            }
            continue
        }

        try {
            Invoke-Git -WorkDir $resolvedRepo -GitArgs @("worktree", "add", $dest, "origin/$branch")
            Write-Info "ok    $branch -> $dest$prNote"
            $ok++
        } catch {
            Write-WarnLine "$branch  (worktree 失敗: $($_.Exception.Message))"
            $failed++
        }
    }
}

Write-Info ""
Write-Info "done  ok=$ok  skip=$skipped  fail=$failed"
Write-Info "今の作業ブランチは変更していません。worktree を Cursor で開いて続きを編集できます。"
if ($ok -eq 0 -and $skipped -gt 0) {
    Write-Info "ブランチが無いエージェントは、クラウド側が commit/push したあとに再実行してください。"
}
exit 0
