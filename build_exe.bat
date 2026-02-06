@echo off
echo ===================================================
echo   SCAN MASTER PRO - BUILD EXECUTABLE
echo ===================================================
echo.
echo 1. Cleaning previous builds...
rmdir /s /q build dist
del /q *.spec

echo.
echo 2. Installing requirements...
pip install -r requirements.txt

echo.
echo 3. Building EXE with PyInstaller...
echo    - Onefile mode
echo    - Windowed (no console)
echo    - Including templates and static files
echo    - Including platform-tools

pyinstaller --noconfirm --onefile --windowed ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --add-data "platform-tools;platform-tools" ^
    --name "ScanMasterPro" ^
    --icon "static/favicon.ico" ^
    app.py

echo.
echo ===================================================
echo   BUILD COMPLETE!
echo   File is located in: dist/ScanMasterPro.exe
echo ===================================================
pause
