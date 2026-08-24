# MediNOTE AI — version locale complète

Cette version combine :

- **Faster-Whisper** pour transcrire les fichiers audio ;
- **EDS-NLP** pour détecter les concepts médicaux français, négations, hypothèses et durées ;
- **Ollama + Qwen3 8B** pour structurer la note sans envoyer les données sur Internet ;
- **Pydantic/JSON Schema** pour valider strictement chaque rubrique ;
- **Flask** pour connecter le moteur Python à l'interface HTML.

## Installation sous Windows

1. Installez **Python 3.11 64 bits** et cochez `Add Python to PATH`.
2. Double-cliquez sur `INSTALLER_WINDOWS.bat`.
3. Si la page Ollama s'ouvre, installez Ollama puis relancez l'installateur.
4. Attendez la fin du téléchargement de `qwen3:8b`.
5. Double-cliquez sur `LANCER_MEDINOTE.bat`.
6. Ouvrez `http://127.0.0.1:5000` si le navigateur ne s'ouvre pas automatiquement.

Ne lancez pas `index.html` directement : la transcription et l'analyse ont besoin du serveur Python.
Conservez également votre fichier `medinote-logo.png` dans ce même dossier pour afficher votre logo d'origine.

## Configuration matérielle

- Qwen3 8B est recommandé avec **16 Go de RAM ou plus**.
- Pour un ordinateur avec 8 Go de RAM, remplacez `qwen3:8b` par `llama3.2:3b`
  dans `LANCER_MEDINOTE.bat`, puis exécutez `ollama pull llama3.2:3b`.
- Le modèle Whisper peut être changé avec `WHISPER_MODEL`: `tiny`, `base`, `small`,
  `medium` ou `large-v3`.

## API locale

- `GET /api/health` : état des composants.
- `POST /api/transcribe` : transcription audio multipart (`audio`, `language`).
- `POST /api/generate-note` : génération depuis un JSON :

```json
{
  "transcript": "Conversation complète...",
  "language": "fr"
}
```

## Confidentialité et sécurité clinique

Le serveur écoute uniquement sur `127.0.0.1`. Les fichiers audio temporaires sont
supprimés après transcription. Les résultats sont des **brouillons** : le médecin
doit obligatoirement les relire, les corriger et les valider. Le système ne remplace
ni l'examen médical, ni le diagnostic, ni la décision thérapeutique.
