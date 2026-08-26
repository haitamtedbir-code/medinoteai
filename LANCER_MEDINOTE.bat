@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERREUR] MediNOTE AI n'est pas installe.
    echo Lancez d'abord INSTALLER_WINDOWS.bat
    pause
    exit /b 1
)

set "PYTHONUTF8=1"

echo =====================================================
echo   MediNOTE AI est disponible sur :
echo   http://127.0.0.1:5000
echo =====================================================
echo.
start "" "http://127.0.0.1:5000"
".venv\Scripts\python.exe" -m waitress --host=127.0.0.1 --port=5000 server:app

pause
