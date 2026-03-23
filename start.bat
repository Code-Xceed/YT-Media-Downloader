@echo off
title YT-Downloader Initializer

:: 1. Check Python installation
python --version >nul 2>&1
if errorlevel 1 goto NoPython

:: 2. Check if main dependencies are natively installed
python -c "import customtkinter, packaging, PIL" >nul 2>&1
if errorlevel 1 goto InstallDeps

:: 3. Jump to executing the app if everything is ready
goto RunApp

:NoPython
echo ==========================================================
echo [ERROR] Python is missing!
echo It appears Python is not installed on this system, or
echo it was not added to your system PATH.
echo.
echo Please download Python from https://www.python.org/
echo IMPORTANT: Check the "Add Python to PATH" box during setup.
echo ==========================================================
pause
exit /b 1

:InstallDeps
echo ==========================================================
echo [INFO] Missing dependencies detected.
echo [INFO] Auto-installing packages from requirements.txt...
echo ==========================================================
pip install -r requirements.txt
if errorlevel 1 goto DepError
echo [SUCCESS] Dependencies installed!
echo.
goto RunApp

:DepError
echo ==========================================================
echo [ERROR] Failed to install required packages!
echo Please check your internet connection and try again.
echo ==========================================================
pause
exit /b 1

:RunApp
echo Starting YT-Downloader App...
start "" pythonw src/main.py
exit
