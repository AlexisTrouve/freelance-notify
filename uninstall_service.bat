@echo off
:: Upwork Service Uninstaller
:: Run as Administrator!

echo ========================================
echo  Upwork Service - Uninstaller
echo ========================================
echo.

:: Check admin
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Please run as Administrator!
    pause
    exit /b 1
)

cd /d "%~dp0"

set SERVICE_NAME=UpworkScraper
set NSSM_PATH=%~dp0nssm.exe

echo Stopping service...
"%NSSM_PATH%" stop %SERVICE_NAME%

echo Removing service...
"%NSSM_PATH%" remove %SERVICE_NAME% confirm

echo.
echo Service removed.
echo Log files are still in this directory if you need them.
echo.
pause
