@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Sample Forge
echo ==========================================
echo   Sample Forge
echo   Model Agnostic Design
echo ==========================================
echo.

cd /d "%~dp0"

REM Detect Python launcher or python.exe
set "PY_CMD=python"
where py >nul 2>&1 && set "PY_CMD=py -3"

REM Create venv if missing
if not exist "venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PY_CMD% -m venv venv || (
    echo Failed to create virtual environment. Ensure Python 3.11+ is installed and on PATH.
    pause
    exit /b 1
  )
)

REM Install/upgrade dependencies
echo Installing dependencies...
echo.
echo Note: first-time setup downloads Python packages (~50-150 MB).
echo This can take a few minutes depending on your internet speed.
echo Please keep this window open until installation completes.
echo.
call "venv\Scripts\python.exe" -m pip install --upgrade pip >nul
call "venv\Scripts\python.exe" -m pip install -r requirements.txt || (
  echo Failed to install requirements. Check your internet connection and retry.
  pause
  exit /b 1
)

echo.
echo Starting application...
echo.
call "venv\Scripts\python.exe" main.py
set "ERR=%ERRORLEVEL%"

if not "%ERR%"=="0" (
  echo App failed to start. Press any key to close.
  pause >nul
)
exit /b %ERR%
