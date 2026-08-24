@echo off
title Installation MediNOTE AI
cd /d "%~dp0"

echo Creation de l'environnement Python...
py -m venv .venv
if errorlevel 1 goto error

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 goto error

echo.
echo Installation terminee avec succes.
echo Lancez maintenant DEMARRER_MEDINOTE.bat
pause
exit /b 0

:error
echo.
echo L'installation a echoue. Verifiez que Python est installe.
pause
exit /b 1
