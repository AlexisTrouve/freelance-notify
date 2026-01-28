@echo off
REM Upwork Scraper - Local Runner
REM Lance le scraping Upwork avec tes queries favorites

echo ========================================
echo   Upwork Scraper - Freelance Notify
echo ========================================
echo.

REM Ferme Firefox si ouvert (requis pour acceder aux cookies)
tasklist /FI "IMAGENAME eq firefox.exe" 2>NUL | find /I /N "firefox.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo [!] Firefox est ouvert. Ferme-le pour continuer.
    echo     Les cookies ne peuvent pas etre lus si Firefox tourne.
    pause
    exit /b 1
)

cd /d "%~dp0"

echo [1] VBA / Excel
echo [2] Python / Automation
echo [3] API / Integration
echo [4] Discord / Bot
echo [5] AI / LLM
echo [6] Custom query
echo [7] Toutes les queries (sequentiel)
echo.
set /p choice="Choix (1-7): "

if "%choice%"=="1" (
    python upwork_adapter.py --visible --query "VBA Excel automation" --num-jobs 20
) else if "%choice%"=="2" (
    python upwork_adapter.py --visible --query "Python scripting automation" --num-jobs 20
) else if "%choice%"=="3" (
    python upwork_adapter.py --visible --query "API integration REST" --num-jobs 20
) else if "%choice%"=="4" (
    python upwork_adapter.py --visible --query "Discord bot" --num-jobs 20
) else if "%choice%"=="5" (
    python upwork_adapter.py --visible --query "ChatGPT LLM AI integration" --num-jobs 20
) else if "%choice%"=="6" (
    set /p custom="Query: "
    python upwork_adapter.py --visible --query "%custom%" --num-jobs 20
) else if "%choice%"=="7" (
    echo.
    echo [*] Scraping VBA/Excel...
    python upwork_adapter.py --visible --query "VBA Excel" --num-jobs 15
    timeout /t 5 >nul

    echo [*] Scraping Python...
    python upwork_adapter.py --visible --query "Python automation" --num-jobs 15
    timeout /t 5 >nul

    echo [*] Scraping API...
    python upwork_adapter.py --visible --query "API integration" --num-jobs 15
    timeout /t 5 >nul

    echo [*] Scraping Discord...
    python upwork_adapter.py --visible --query "Discord bot" --num-jobs 15
) else (
    echo Choix invalide
)

echo.
echo ========================================
echo   Scraping termine!
echo ========================================
pause
