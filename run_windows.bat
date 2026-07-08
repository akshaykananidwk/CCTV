@echo off
REM  i-Footege Intelligence - Launcher (Windows)
title i-Footege Intelligence
cd /d "%~dp0"
if not exist venv\Scripts\activate.bat (
    echo [ERROR] Not installed yet. Run install_windows.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
pythonw i_footege_intelligence.py
if errorlevel 1 python i_footege_intelligence.py
