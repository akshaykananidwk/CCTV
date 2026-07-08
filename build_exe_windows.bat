@echo off
REM ============================================================
REM  i-Footege Intelligence - Build standalone EXE (Windows)
REM ------------------------------------------------------------
REM  Run install_windows.bat FIRST, then run this.
REM  Output: dist\i-Footege\i-Footege.exe  (copy whole folder)
REM ============================================================
title i-Footege Intelligence - EXE Builder
cd /d "%~dp0"
if not exist venv\Scripts\activate.bat (
    echo [ERROR] Run install_windows.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
pip install pyinstaller

pyinstaller --noconfirm --windowed --name "i-Footege" ^
  --collect-all ultralytics ^
  --collect-all customtkinter ^
  --collect-all reportlab ^
  --hidden-import=PIL._tkinter_finder ^
  i_footege_intelligence.py

echo.
echo  ==============================================
echo   Build finished!
echo   Your software:  dist\i-Footege\i-Footege.exe
echo   Copy the whole "dist\i-Footege" folder to any
echo   PC and double-click i-Footege.exe (no Python
echo   needed on that PC).
echo  ==============================================
pause
