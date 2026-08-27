@echo off
REM D:\dev 配下に配置する。キーはチャットに貼らない。
if "%CURSOR_API_KEY%"=="" (
  echo error CURSOR_API_KEY が未設定です。チャットにキーを貼らないでください.
  echo.
  echo 発行: https://cursor.com/dashboard/api
  echo 同じ cmd で:
  echo   set CURSOR_API_KEY=発行したキー
  echo PowerShell なら:
  echo   $env:CURSOR_API_KEY = "発行したキー"
  echo   powershell -ExecutionPolicy Bypass -File "%~dp0sync-cloud-agents.ps1"
  exit /b 2
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync-cloud-agents.ps1" %*
exit /b %ERRORLEVEL%
