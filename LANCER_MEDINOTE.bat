@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERREUR] MediNOTE AI n'est pas installe.
    echo Lancez d'abord INSTALLER_WINDOWS.bat
    pause
    exit /b 1
)

where ollama >nul 2>nul
if errorlevel 1 (
    echo [ERREUR] Ollama est introuvable. Lancez INSTALLER_WINDOWS.bat
    pause
    exit /b 1
)

curl -s --max-time 2 http://127.0.0.1:11434/api/tags >nul 2>nul
if errorlevel 1 (
    echo Demarrage d'Ollama...
    start "Ollama" /min ollama serve
    timeout /t 5 /nobreak >nul
)

set "OLLAMA_MODEL=qwen3:8b"
set "OLLAMA_BASE_URL=http://127.0.0.1:11434"
set "WHISPER_MODEL=small"
set "WHISPER_DEVICE=cpu"
set "WHISPER_COMPUTE_TYPE=int8"
set "PYTHONUTF8=1"

echo =====================================================
echo   MediNOTE AI est disponible sur :
echo   http://127.0.0.1:5000
echo =====================================================
echo.
start "" "http://127.0.0.1:5000"
".venv\Scripts\python.exe" -m waitress --host=127.0.0.1 --port=5000 server:app

pause
