@echo off
REM ============================================================
REM  Premarket Finance Dispatch - One-Click Start
REM  - Pure ASCII to avoid GBK / UTF-8 codepage issues
REM ============================================================
title Premarket Finance Dispatch - One-Click Start
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ============================================================
echo   Premarket Finance Dispatch  v1.0.0
echo   One-Click Start
echo ============================================================
echo.

REM ---------- Check Python ----------
where python >nul 2>&1
if errorlevel 1 (
    echo [X] Python not found. Install Python 3.8+ first.
    echo     Download: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo [OK] Python !PYVER!

REM ---------- Check dependencies ----------
echo.
echo [1/3] Checking Python dependencies...
python -c "import flask, requests, schedule" >nul 2>&1
if errorlevel 1 (
    echo [!] Missing deps, installing requirements.txt ...
    python -m pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo [X] Install failed. Run manually:  pip install -r requirements.txt
        pause
        exit /b 1
    )
)
echo [OK] All deps present

REM ---------- Check china-finance-rss on :8053 ----------
echo.
echo [2/3] Checking china-finance-rss on port 8053...
curl -s -o nul -w "%%{http_code}" http://localhost:8053/ 2>nul | findstr "200" >nul
if not errorlevel 1 (
    echo [OK] china-finance-rss already running on :8053
) else (
    if not exist "china-finance-rss\server.py" (
        echo [X] china-finance-rss\server.py not found.
        echo     Clone first:  git clone https://github.com/yuxuan-made/china-finance-rss.git
        pause
        exit /b 1
    )
    echo [!] Starting china-finance-rss in a new window...
    start "china-finance-rss" cmd /k "cd /d %~dp0china-finance-rss && echo === china-finance-rss (do NOT close) === && python server.py"
    echo     Waiting 5s for service to be ready...
    timeout /t 5 /nobreak >nul

    curl -s -o nul -w "%%{http_code}" http://localhost:8053/ 2>nul | findstr "200" >nul
    if not errorlevel 1 (
        echo [OK] china-finance-rss started
    ) else (
        echo [!] RSS not ready in 5s. Web will still start; first refresh may fail.
    )
)

REM ---------- Start Flask ----------
echo.
echo [3/3] Starting Web service...
echo.
echo ============================================================
echo   Browser:  http://localhost:5000
echo   DO NOT close the china-finance-rss window.
echo   Press Ctrl+C in THIS window to stop Web.
echo ============================================================
echo.

echo Opening browser in 3s...
timeout /t 3 /nobreak >nul
start "" http://localhost:5000

python app.py
pause

endlocal
