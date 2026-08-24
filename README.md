# MediNOTE AI — transcription locale avec Whisper

Cette version permet de :

- importer un fichier MP3, WAV, M4A, MP4, WEBM, OGG ou FLAC ;
- écouter et supprimer l'audio ;
- transcrire automatiquement le fichier avec Whisper en local ;
- modifier la transcription ;
- générer, valider, sauvegarder et exporter la note médicale.

## Installation sous Windows

Méthode simple :

1. Double-cliquez sur `INSTALLER_WINDOWS.bat` une seule fois.
2. Double-cliquez ensuite sur `DEMARRER_MEDINOTE.bat` pour utiliser l'application.

Méthode manuelle :

Ouvrez PowerShell dans ce dossier, puis exécutez :

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Ouvrez ensuite cette adresse dans Chrome ou Edge :

```text
http://127.0.0.1:5000
```

Ne lancez pas `index.html` directement : la transcription des fichiers passe par le serveur Python.

## Première transcription

Au premier lancement, Faster-Whisper télécharge automatiquement le modèle `small`. Cette première transcription peut donc être plus lente. Les utilisations suivantes réutilisent le modèle déjà téléchargé.

## Choisir un autre modèle

Le modèle `small` offre un bon équilibre entre précision et vitesse. Avant de lancer le serveur, vous pouvez choisir :

```powershell
$env:WHISPER_MODEL="base"    # plus rapide
$env:WHISPER_MODEL="medium"  # plus précis, mais plus lourd
python app.py
```

La configuration par défaut utilise le processeur avec `int8`. Pour un GPU NVIDIA correctement configuré :

```powershell
$env:WHISPER_DEVICE="cuda"
$env:WHISPER_COMPUTE_TYPE="float16"
python app.py
```

## Confidentialité

L'audio est traité sur votre ordinateur. Le serveur le place seulement dans un dossier temporaire pendant la transcription, puis le supprime automatiquement. Pour un usage médical réel, ajoutez l'authentification, le chiffrement, le contrôle d'accès et les règles de conservation adaptées à votre établissement.
