"""Local MediNOTE AI server powered by Faster-Whisper.

The audio file is written to a temporary directory for transcription and is
deleted automatically when the request finishes.
"""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from faster_whisper import WhisperModel
from werkzeug.utils import secure_filename


PROJECT_DIR = Path(__file__).resolve().parent
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".flac"}
MAX_AUDIO_SIZE = 50 * 1024 * 1024

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_AUDIO_SIZE

_model: WhisperModel | None = None
_model_lock = threading.Lock()


def get_whisper_model() -> WhisperModel:
    """Load the configured model once, on the first transcription request."""
    global _model

    if _model is None:
        with _model_lock:
            if _model is None:
                model_name = os.getenv("WHISPER_MODEL", "small")
                device = os.getenv("WHISPER_DEVICE", "cpu")
                compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
                _model = WhisperModel(
                    model_name,
                    device=device,
                    compute_type=compute_type,
                )

    return _model


@app.get("/")
def index():
    return send_from_directory(PROJECT_DIR, "index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "engine": "faster-whisper"})


@app.post("/api/transcribe")
def transcribe_audio():
    audio = request.files.get("audio")

    if audio is None or not audio.filename:
        return jsonify({"error": "Aucun fichier audio reçu."}), 400

    safe_name = secure_filename(audio.filename)
    suffix = Path(safe_name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        return jsonify({
            "error": "Format non accepté. Utilisez MP3, WAV, M4A, MP4, WEBM, OGG ou FLAC."
        }), 415

    requested_language = request.form.get("language", "").strip().lower()
    language = requested_language if requested_language in {"fr", "en"} else None

    try:
        with tempfile.TemporaryDirectory(prefix="medinote-") as temp_dir:
            audio_path = Path(temp_dir) / (safe_name or f"consultation{suffix}")
            audio.save(audio_path)

            segments, info = get_whisper_model().transcribe(
                str(audio_path),
                language=language,
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=False,
            )

            text = " ".join(segment.text.strip() for segment in segments).strip()

        return jsonify({
            "text": text,
            "language": info.language,
            "language_probability": round(float(info.language_probability), 4),
            "duration": round(float(info.duration), 2),
        })

    except Exception as error:
        app.logger.exception("Whisper transcription failed")
        return jsonify({
            "error": "Impossible de transcrire ce fichier. Vérifiez l'audio puis réessayez.",
            "details": str(error),
        }), 500


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify({"error": "Le fichier dépasse la limite de 50 MB."}), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
