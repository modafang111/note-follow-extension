@echo off
setlocal
cd /d "%~dp0"

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
echo OK
echo Chrome: chrome://extensions  ->  Reload
echo.
pause
exit /b 0

:error
echo.
echo FAILED. Keep this window and send the text.
echo.
pause
exit /b 1
