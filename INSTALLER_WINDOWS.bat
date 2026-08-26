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

echo [3/4] Installation de Gemini, Pydantic et Flask...
echo Suppression des anciens composants locaux bloques par Windows...
".venv\Scripts\python.exe" -m pip uninstall -y faster-whisper av edsnlp spacy thinc preshed cymem murmurhash >nul 2>nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :install_error

if not exist ".env" (
    echo [4/4] Configuration de Gemini...
    copy /y ".env.example" ".env" >nul
    echo.
    echo Ajoutez votre NOUVELLE cle Google AI Studio dans le fichier .env.
    echo N'utilisez pas une cle deja publiee ou partagee.
    start "" notepad ".env"
    pause
) else (
    echo [4/4] Configuration Gemini deja presente.
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
