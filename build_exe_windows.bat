@echo off
REM ============================================================
REM  Krishna Intelligence - Build standalone EXE (Windows)
REM ------------------------------------------------------------
REM  Run install_windows.bat FIRST, then run this.
REM  Output: dist\Krishna-Intelligence\Krishna-Intelligence.exe
REM ============================================================
title Krishna Intelligence - EXE Builder
cd /d "%~dp0"
if not exist venv\Scripts\activate.bat (
    echo [ERROR] Run install_windows.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
pip install pyinstaller

pyinstaller --noconfirm --windowed --name "Krishna-Intelligence" ^
  --collect-all ultralytics ^
  --collect-all customtkinter ^
  --collect-all reportlab ^
  --hidden-import=PIL._tkinter_finder ^
  krishna_intelligence.py

echo.
echo  ==============================================
echo   Build finished!
echo   Your software:  dist\Krishna-Intelligence\Krishna-Intelligence.exe
echo   Copy the whole "dist\Krishna-Intelligence" folder to any
echo   PC and double-click the exe (no Python needed there).
echo  ==============================================
pause
