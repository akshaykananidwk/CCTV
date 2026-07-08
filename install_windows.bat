@echo off
REM ============================================================
REM  Krishna Intelligence - One-time installer (Windows)
REM  LCB Technical Cell, Devbhoomi Dwarka
REM ------------------------------------------------------------
REM  Needs: Python 3.10+ installed from https://www.python.org
REM  (During Python setup, tick "Add Python to PATH")
REM ============================================================
title Krishna Intelligence - Installer
echo.
echo  ==============================================
echo   Krishna Intelligence - Installation
echo  ==============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found!
    echo  Please install Python 3.10+ from https://www.python.org
    echo  and tick "Add Python to PATH" during setup.
    pause
    exit /b 1
)

echo  [1/3] Creating virtual environment...
python -m venv venv
if errorlevel 1 ( echo [ERROR] venv creation failed & pause & exit /b 1 )

echo  [2/3] Installing packages (this can take 5-15 minutes)...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 ( echo [ERROR] Package install failed - check internet & pause & exit /b 1 )

echo  [3/3] Done!
echo.
echo  ==============================================
echo   Installation complete!
echo   Double-click  run_windows.bat  to start.
echo   (First start downloads the AI model ~22 MB,
echo    so internet is needed once.)
echo  ==============================================
echo.
pause
