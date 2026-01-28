@echo off
:: Upwork Service Installer using NSSM
:: Run as Administrator!

echo ========================================
echo  Upwork Service - NSSM Installer
echo ========================================
echo.

:: Check admin
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Please run as Administrator!
    echo Right-click this file and select "Run as administrator"
    pause
    exit /b 1
)

cd /d "%~dp0"

set SERVICE_NAME=UpworkScraper
set NSSM_PATH=%~dp0nssm.exe
set PYTHON_PATH=C:\Users\alexi\AppData\Local\Programs\Python\Python312\python.exe
set SCRIPT_PATH=%~dp0upwork_service.py
set WORKING_DIR=%~dp0

:: Check files exist
if not exist "%NSSM_PATH%" (
    echo [ERROR] nssm.exe not found in current directory
    pause
    exit /b 1
)

if not exist "%SCRIPT_PATH%" (
    echo [ERROR] upwork_service.py not found
    pause
    exit /b 1
)

echo [1/4] Stopping existing service if running...
"%NSSM_PATH%" stop %SERVICE_NAME% >nul 2>&1
"%NSSM_PATH%" remove %SERVICE_NAME% confirm >nul 2>&1

echo [2/4] Installing service...
"%NSSM_PATH%" install %SERVICE_NAME% "%PYTHON_PATH%" "%SCRIPT_PATH%"

echo [3/4] Configuring service...
:: Set working directory
"%NSSM_PATH%" set %SERVICE_NAME% AppDirectory "%WORKING_DIR%"

:: Set startup type to Automatic (Delayed)
"%NSSM_PATH%" set %SERVICE_NAME% Start SERVICE_DELAYED_AUTO_START

:: Configure logging
"%NSSM_PATH%" set %SERVICE_NAME% AppStdout "%WORKING_DIR%upwork_service_stdout.log"
"%NSSM_PATH%" set %SERVICE_NAME% AppStderr "%WORKING_DIR%upwork_service_stderr.log"
"%NSSM_PATH%" set %SERVICE_NAME% AppStdoutCreationDisposition 4
"%NSSM_PATH%" set %SERVICE_NAME% AppStderrCreationDisposition 4
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateFiles 1
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateBytes 1048576

:: Set description
"%NSSM_PATH%" set %SERVICE_NAME% Description "Upwork job scraper - checks every 3 hours and notifies Discord"

:: Set restart behavior
"%NSSM_PATH%" set %SERVICE_NAME% AppExit Default Restart
"%NSSM_PATH%" set %SERVICE_NAME% AppRestartDelay 60000

echo [4/4] Starting service...
"%NSSM_PATH%" start %SERVICE_NAME%

echo.
echo ========================================
echo  Installation Complete!
echo ========================================
echo.
echo Service Name: %SERVICE_NAME%
echo Status: Starting...
echo.
echo Commands:
echo   Start:   nssm start %SERVICE_NAME%
echo   Stop:    nssm stop %SERVICE_NAME%
echo   Status:  nssm status %SERVICE_NAME%
echo   Logs:    type upwork_service.log
echo   Edit:    nssm edit %SERVICE_NAME%
echo.
echo The service will now run automatically on boot.
echo Check upwork_service.log for output.
echo.
pause
