@echo off
title MediNOTE AI
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo MediNOTE AI n'est pas encore installe.
    echo Lancez d'abord INSTALLER_WINDOWS.bat
    pause
    exit /b 1
)

start "" "http://127.0.0.1:5000"
".venv\Scripts\python.exe" -m waitress --host=127.0.0.1 --port=5000 server:app
pause
