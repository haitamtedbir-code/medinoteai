@echo off
setlocal
cd /d "%~dp0"

echo =====================================================
echo   MediNOTE AI - Installation locale
echo =====================================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo [ERREUR] Python est introuvable.
    echo Installez Python 3.11 64 bits puis cochez "Add Python to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creation de l'environnement Python...
    py -3.11 -m venv .venv
    if errorlevel 1 (
        echo Python 3.11 est recommande. Verification de Python 3...
        py -3 -m venv .venv
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo [ERREUR] Impossible de creer l'environnement Python.
    pause
    exit /b 1
)

echo [2/4] Mise a jour de pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip wheel "setuptools<81"
if errorlevel 1 goto :install_error

echo [3/4] Installation de Faster-Whisper, EDS-NLP, Pydantic et Flask...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :install_error

where ollama >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ACTION REQUISE] Ollama n'est pas installe.
    echo La page officielle va s'ouvrir. Installez Ollama, puis relancez ce fichier.
    start "" "https://ollama.com/download/windows"
    pause
    exit /b 1
)

echo [4/4] Telechargement du modele Qwen3 8B...
ollama pull qwen3:8b
if errorlevel 1 (
    echo [ERREUR] Le modele Qwen3 8B n'a pas pu etre telecharge.
    echo Verifiez votre connexion et que l'application Ollama est lancee.
    pause
    exit /b 1
)

echo.
echo =====================================================
echo   Installation terminee avec succes.
echo   Lancez maintenant LANCER_MEDINOTE.bat
echo =====================================================
pause
exit /b 0

:install_error
echo.
echo [ERREUR] L'installation Python a echoue.
echo Verifiez que Python est en version 3.10 ou 3.11 et relancez ce fichier.
pause
exit /b 1
