@echo off
title SCAN MASTER PRO Server
echo ==================================================
echo      SCAN MASTER PRO - SYSTEM STARTUP
echo ==================================================

echo [1/3] Checking dependencies...
python -m pip install -r requirements.txt > nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Could not install dependencies. Please check Python installation.
    pause
    exit
)
echo Dependencies OK.

echo [2/3] Cleaning up temporary files...
if exist preview_temp.png del preview_temp.png
if exist *.pyc del *.pyc

echo [3/3] Starting Server...
echo.
echo Server is running at: http://127.0.0.1:5000
echo (Keep this window open while using the app)
echo.

python app.py
pause