@echo off
REM  Krishna Intelligence - Launcher (Windows)
title Krishna Intelligence
cd /d "%~dp0"
if not exist venv\Scripts\activate.bat (
    echo [ERROR] Not installed yet. Run install_windows.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
pythonw krishna_intelligence.py
if errorlevel 1 python krishna_intelligence.py
