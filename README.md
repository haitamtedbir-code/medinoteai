# MediNOTE AI — version 100 % Gemini

Cette version combine :

- **Gemini** pour transcrire les fichiers MP3, WAV, M4A, MP4, WEBM, OGG et FLAC ;
- **Gemini Interactions API** pour structurer les notes et alimenter le bouton flottant de conversation médicale ;
- **Pydantic/JSON Schema** pour valider strictement chaque rubrique ;
- **Flask** pour connecter le moteur Python à l'interface HTML.

Faster-Whisper, PyAV, EDS-NLP, spaCy et Ollama ne sont plus utilisés. Cette version
évite donc les fichiers natifs `.pyd` que le contrôle intelligent Windows bloquait.

## Installation sous Windows

1. Installez **Python 3.11 64 bits** et cochez `Add Python to PATH`.
2. Double-cliquez sur `INSTALLER_WINDOWS.bat`.
3. Lorsque `.env` s'ouvre, remplacez `remplacez-par-votre-nouvelle-cle` par une
   **nouvelle** clé Google AI Studio, puis enregistrez le fichier. Ne réutilisez
   jamais une clé déjà publiée.
4. Vérifiez que `GEMINI_MODEL=gemini-3.5-flash-lite`, puis enregistrez le fichier.
5. Double-cliquez sur `LANCER_MEDINOTE.bat`.
6. Ouvrez `http://127.0.0.1:5000` si le navigateur ne s'ouvre pas automatiquement.

Ne lancez pas `index.html` directement : la transcription et l'analyse ont besoin du serveur Python.
Conservez également votre fichier `medinote-logo.png` dans ce même dossier pour afficher votre logo d'origine.

## Configuration

- Une connexion Internet est nécessaire pour le chat et la génération des notes avec Gemini.
- Elle est également nécessaire pour la transcription audio Gemini.
- Aucun modèle IA local n'est nécessaire.

## API locale

- `GET /api/health` : état des composants.
- `POST /api/chat` : conversation médicale Gemini avec historique court.
- `POST /api/transcribe` : transcription audio multipart (`audio`, `language`).
- `POST /api/generate-note` : génération depuis un JSON :

```json
{
  "transcript": "Conversation complète...",
  "language": "fr"
}
```

## Confidentialité et sécurité clinique

Le serveur écoute uniquement sur `127.0.0.1`. La clé Gemini reste dans `.env`, côté
serveur, et `.env` est exclu de Git. Chaque fichier audio est envoyé temporairement à
Gemini puis une suppression immédiate est demandée après la transcription. La transcription,
le chat et la génération des notes utilisent donc un service en ligne : n'y envoyez aucune
donnée identifiant un patient sans base légale, consentement et garanties de protection
appropriées. Les résultats sont des **brouillons** : le médecin doit
obligatoirement les relire, les corriger et les valider. Le système ne remplace ni
l'examen médical, ni le diagnostic, ni la décision thérapeutique.
