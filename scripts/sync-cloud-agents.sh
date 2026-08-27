#!/usr/bin/env bash
# Cursor Cloud Agent が push したブランチを git worktree に一括取り込みする。
# Git リポジトリではない場所からでも動く。既定の配置先は D:\dev（Git Bash では /d/dev）。
# Windows は PowerShell 版を推奨。
set -euo pipefail

API_BASE="${CURSOR_API_BASE:-https://api.cursor.com}"
REPO_URL="${REPO_URL:-https://github.com/modafang111/note-follow-extension.git}"
LIST_ONLY=0
NO_CLONE=0
REPO_PATH=""
DEV_ROOT="${CURSOR_SYNC_ROOT:-}"
WT_ROOT=""

default_dev_root() {
  if [[ -n "${CURSOR_SYNC_ROOT:-}" ]]; then
    printf '%s\n' "$CURSOR_SYNC_ROOT"
    return
  fi
  if [[ -d /d/dev ]]; then
    printf '%s\n' /d/dev
    return
  fi
  if [[ -d D:/dev ]]; then
    printf '%s\n' D:/dev
    return
  fi
  case "$(uname -s 2>/dev/null || true)" in
    MINGW*|MSYS*|CYGWIN*) printf '%s\n' /d/dev; return ;;
  esac
  printf '%s\n' "${HOME}/dev"
}

usage() {
  cat <<'EOF'
使い方:
  CURSOR_API_KEY=... ./scripts/sync-cloud-agents.sh [options]

Options:
  --repo-path PATH   Git リポジトリのパス
  --dev-root DIR     プログラムの配置先（省略時は D:\\dev または /d/dev）
  --worktree-root D  worktree の作成先（省略時は <dev-root>/cursor-cloud-worktrees/note-follow-extension）
  --list-only        checkout せずブランチ一覧だけ出す
  --no-clone         リポジトリが無いとき clone しない
  -h, --help         このヘルプ

CURSOR_API_KEY はチャットに貼らず、環境変数で渡してください。
発行: https://cursor.com/dashboard/api
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-path) REPO_PATH="${2:-}"; shift 2 ;;
    --dev-root) DEV_ROOT="${2:-}"; shift 2 ;;
    --worktree-root) WT_ROOT="${2:-}"; shift 2 ;;
    --list-only) LIST_ONLY=1; shift ;;
    --no-clone) NO_CLONE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 1 ;;
  esac
done

if ! command -v git >/dev/null 2>&1; then
  echo "error git が見つかりません。" >&2
  exit 1
fi

if [[ -z "${CURSOR_API_KEY:-}" ]]; then
  echo "error CURSOR_API_KEY が未設定です。チャットにキーを貼らないでください。" >&2
  echo "" >&2
  echo "発行: https://cursor.com/dashboard/api" >&2
  echo "Git Bash:" >&2
  echo '  export CURSOR_API_KEY="（発行したキー）"' >&2
  echo "PowerShell:" >&2
  echo '  $env:CURSOR_API_KEY = "（発行したキー）"' >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "error python が必要です。Windows では scripts/sync-cloud-agents.ps1 を使ってください。" >&2
  exit 1
fi
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python

JSON_FILE="$(mktemp "${TMPDIR:-/tmp}/cursor-cloud-sync.XXXXXX")"
trap 'rm -f "$JSON_FILE"' EXIT

api_get() {
  local path="$1"
  local code
  code="$(curl -sS -o "$JSON_FILE" -w "%{http_code}" -u "${CURSOR_API_KEY}:" "${API_BASE}${path}")"
  if [[ "$code" == "401" || "$code" == "403" ]]; then
    echo "error Cursor API がキーを拒否しました (HTTP ${code})。" >&2
    exit 2
  fi
  if [[ "$code" != "200" ]]; then
    echo "error Cursor API 失敗 HTTP ${code}: ${API_BASE}${path}" >&2
    cat "$JSON_FILE" >&2 || true
    exit 1
  fi
}

slug() {
  "$PY" -c 'import sys; u=sys.argv[1].strip();
u=u.replace("https://","").replace("http://","");
u=u[:-4] if u.endswith(".git") else u
print(u.strip("/").lower())' "$1"
}

is_git_repo() {
  git -C "$1" rev-parse --is-inside-work-tree >/dev/null 2>&1
}

if [[ -z "$DEV_ROOT" ]]; then
  DEV_ROOT="$(default_dev_root)"
fi
DEFAULT_CLONE="${DEV_ROOT}/note-follow-extension"

resolve_repo() {
  if [[ -n "$REPO_PATH" ]]; then
    if ! is_git_repo "$REPO_PATH"; then
      echo "error --repo-path が Git リポジトリではありません: $REPO_PATH" >&2
      exit 1
    fi
    git -C "$REPO_PATH" rev-parse --show-toplevel
    return
  fi
  if is_git_repo "$DEFAULT_CLONE"; then
    git -C "$DEFAULT_CLONE" rev-parse --show-toplevel
    return
  fi
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git rev-parse --show-toplevel
    return
  fi
  if [[ "$NO_CLONE" -eq 1 ]]; then
    echo "error Git リポジトリが見つかりません。--repo-path を指定するか clone してください。" >&2
    exit 1
  fi
  echo "リポジトリが無いのでクローンします: $REPO_URL" >&2
  echo "  -> $DEFAULT_CLONE" >&2
  mkdir -p "$DEV_ROOT"
  git clone "$REPO_URL" "$DEFAULT_CLONE"
  echo "$DEFAULT_CLONE"
}

REPO="$(resolve_repo)"
TARGET_SLUG="$(slug "$REPO_URL")"
ORIGIN_URL="$(git -C "$REPO" remote get-url origin)"
ORIGIN_SLUG="$(slug "$ORIGIN_URL")"
WT_ROOT="${WT_ROOT:-${DEV_ROOT}/cursor-cloud-worktrees/note-follow-extension}"
mkdir -p "$WT_ROOT"

echo "repo     $REPO"
echo "origin   $ORIGIN_URL"
echo "worktrees $WT_ROOT"
echo "fetch しています..."
git -C "$REPO" fetch origin --prune

api_get "/v1/agents?limit=100&includeArchived=false"
mapfile -t AGENT_IDS < <("$PY" - "$JSON_FILE" <<'PY'
import json, sys
d=json.load(open(sys.argv[1]))
items=d.get("items") or d.get("agents") or []
for a in items:
    print(a.get("id",""))
PY
)

ok=0; skipped=0; failed=0
declare -A SEEN=()

for agent_id in "${AGENT_IDS[@]}"; do
  [[ -z "$agent_id" ]] && continue
  api_get "/v1/agents/${agent_id}"
  latest="$("$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("latestRunId") or "")' "$JSON_FILE")"
  name="$("$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("name") or d.get("id") or "")' "$JSON_FILE")"
  if [[ -z "$latest" ]]; then
    echo "skip  ${name}  (run がまだ無い)"
    skipped=$((skipped+1))
    continue
  fi
  api_get "/v1/agents/${agent_id}/runs/${latest}"
  while IFS=$'\t' read -r branch repo pr; do
    [[ -z "$branch" ]] && continue
    bslug="$(slug "$repo")"
    if [[ -n "$bslug" && "$bslug" != "$TARGET_SLUG" && "$bslug" != "$ORIGIN_SLUG" ]]; then
      continue
    fi
    if [[ -n "${SEEN[$branch]:-}" ]]; then
      continue
    fi
    SEEN[$branch]=1
    pr_note=""
    [[ -n "$pr" ]] && pr_note="  PR ${pr}"
    if [[ "$LIST_ONLY" -eq 1 ]]; then
      echo "list  ${branch}${pr_note}"
      ok=$((ok+1))
      continue
    fi
    if ! git -C "$REPO" show-ref --verify --quiet "refs/remotes/origin/${branch}"; then
      echo "skip  ${branch}  (origin にまだ無い)${pr_note}"
      skipped=$((skipped+1))
      continue
    fi
    safe="${branch//\//-}"
    dest="${WT_ROOT}/${safe}"
    if [[ -d "$dest" ]]; then
      if git -C "$dest" fetch origin "$branch" && git -C "$dest" checkout "$branch" && git -C "$dest" pull --ff-only; then
        echo "upd   ${branch} -> ${dest}${pr_note}"
        ok=$((ok+1))
      else
        echo "skip  ${branch}  (更新失敗)"
        failed=$((failed+1))
      fi
      continue
    fi
    if git -C "$REPO" worktree add "$dest" "origin/${branch}"; then
      echo "ok    ${branch} -> ${dest}${pr_note}"
      ok=$((ok+1))
    else
      echo "skip  ${branch}  (worktree 失敗)"
      failed=$((failed+1))
    fi
  done < <("$PY" - "$JSON_FILE" <<'PY'
import json, sys
d=json.load(open(sys.argv[1]))
branches=(d.get("git") or {}).get("branches") or []
for b in branches:
    print("{}\t{}\t{}".format(b.get("branch") or "", b.get("repoUrl") or "", b.get("prUrl") or ""))
PY
)
done

echo
echo "done  ok=${ok}  skip=${skipped}  fail=${failed}"
echo "今の作業ブランチは変更していません。"
