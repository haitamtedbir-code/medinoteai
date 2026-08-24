@echo off
title MediNOTE AI - Whisper local
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo MediNOTE AI n'est pas encore installe.
    echo Lancez d'abord INSTALLER_WINDOWS.bat
    pause
    exit /b 1
)

start "" "http://127.0.0.1:5000"
call .venv\Scripts\activate.bat
python app.py
pause
