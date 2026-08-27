@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Cloud Agent 同期

REM D:\dev 配下で使う Windows バッチ。ダブルクリック可。キーはチャットに貼らない。

set "DEV_ROOT=D:\dev"
if defined CURSOR_SYNC_ROOT set "DEV_ROOT=%CURSOR_SYNC_ROOT%"
set "REPO_DIR=%DEV_ROOT%\note-follow-extension"
set "REPO_URL=https://github.com/modafang111/note-follow-extension.git"
set "PS1="
set "GIT="
set "PAUSE_AT_END=1"
set "ARGS="
set "RC=0"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="/nopause" (
  set "PAUSE_AT_END=0"
  shift
  goto parse_args
)
if /I "%~1"=="-nopause" (
  set "PAUSE_AT_END=0"
  shift
  goto parse_args
)
set "ARGS=!ARGS! %1"
shift
goto parse_args
:args_done

echo.
echo === Cloud Agent 同期 ===
echo 配置先: %DEV_ROOT%
echo.

call :find_git
if not defined GIT (
  echo error git が見つかりません。Git for Windows を入れてから、このバッチを再実行してください。
  echo   https://git-scm.com/download/win
  goto fail
)

if not exist "%DEV_ROOT%\" (
  echo D:\dev が無いので作成します。
  mkdir "%DEV_ROOT%" 2>nul
  if not exist "%DEV_ROOT%\" (
    echo error %DEV_ROOT% を作成できませんでした。
    goto fail
  )
)

if not exist "%REPO_DIR%\.git\" (
  echo リポジトリが無いのでクローンします。
  echo   %REPO_URL%
  echo   -^> %REPO_DIR%
  "%GIT%" clone "%REPO_URL%" "%REPO_DIR%"
  if errorlevel 1 (
    echo error clone に失敗しました。
    goto fail
  )
)

call :find_ps1
if not defined PS1 (
  echo scripts\sync-cloud-agents.ps1 がまだ無いので、リモートを取得します。
  "%GIT%" -C "%REPO_DIR%" fetch origin
  call :find_ps1
)
if not defined PS1 (
  echo error %REPO_DIR%\scripts\sync-cloud-agents.ps1 が見つかりません。
  echo この PR ブランチを checkout してから再実行してください。
  echo   git -C "%REPO_DIR%" fetch origin
  echo   git -C "%REPO_DIR%" checkout cursor/windows-cloud-agent-sync-10be
  goto fail
)

copy /Y "%~f0" "%DEV_ROOT%\sync-cloud-agents.bat" >nul 2>&1
if exist "%DEV_ROOT%\sync-cloud-agents.bat" (
  echo 次回から D:\dev\sync-cloud-agents.bat をダブルクリックしても実行できます。
  echo.
)

call :ensure_api_key
if errorlevel 1 goto fail

echo 同期を開始します...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -DevRoot "%DEV_ROOT%" !ARGS!
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo error 同期に失敗しました。終了コード %RC%
  goto fail
)
echo 完了しました。worktree は %DEV_ROOT%\cursor-cloud-worktrees\note-follow-extension
goto end

:find_git
where git >nul 2>&1
if not errorlevel 1 (
  for /f "delims=" %%G in ('where git') do (
    set "GIT=%%G"
    goto :eof
  )
)
if exist "C:\Program Files\Git\cmd\git.exe" (
  set "GIT=C:\Program Files\Git\cmd\git.exe"
  goto :eof
)
if exist "C:\Program Files (x86)\Git\cmd\git.exe" (
  set "GIT=C:\Program Files (x86)\Git\cmd\git.exe"
  goto :eof
)
goto :eof

:find_ps1
if exist "%~dp0sync-cloud-agents.ps1" (
  set "PS1=%~dp0sync-cloud-agents.ps1"
  goto :eof
)
if exist "%REPO_DIR%\scripts\sync-cloud-agents.ps1" (
  set "PS1=%REPO_DIR%\scripts\sync-cloud-agents.ps1"
  goto :eof
)
set "PS1="
goto :eof

:ensure_api_key
if defined CURSOR_API_KEY exit /b 0
echo CURSOR_API_KEY が未設定です。チャットには貼らないでください。
echo 発行: https://cursor.com/dashboard/api
echo.
set "CURSOR_API_KEY="
set /p CURSOR_API_KEY=APIキーを入力して Enter:
if not defined CURSOR_API_KEY (
  echo error キーが入力されませんでした。
  exit /b 1
)
setx CURSOR_API_KEY "%CURSOR_API_KEY%" >nul
if errorlevel 1 (
  echo 警告: ユーザー環境変数への保存に失敗しました。この窓のあいだだけ使います。
) else (
  echo ユーザー環境変数に保存しました。新しい窓からは自動で使われます。
)
echo.
exit /b 0

:fail
set "RC=1"
echo.
echo 失敗したので終了します。
goto end

:end
if "%PAUSE_AT_END%"=="1" (
  echo.
  pause
)
exit /b %RC%
