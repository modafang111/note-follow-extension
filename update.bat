@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo.
echo [1/3] git pull
git pull
if errorlevel 1 goto :error

echo.
echo [2/3] npm install
call npm install
if errorlevel 1 goto :error

echo.
echo [3/3] npm run build
call npm run build
if errorlevel 1 goto :error

echo.
echo 完了しました。
echo Chrome の chrome://extensions を開いて、拡張を再読み込みしてください。
echo.
pause
exit /b 0

:error
echo.
echo 途中で失敗しました。この画面を残して内容を送ってください。
echo.
pause
exit /b 1
