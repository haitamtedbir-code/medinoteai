"""Serveur local MediNOTE AI.

Pipeline:
    Audio -> Faster-Whisper -> transcription
    Transcription -> EDS-NLP -> signaux cliniques français
    Signaux + transcription -> Ollama/Qwen3 -> JSON structuré
    JSON -> Pydantic -> note médicale à faire valider par le médecin

Les fichiers audio sont traités dans un dossier temporaire automatiquement
supprimé à la fin de chaque requête.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Literal

import requests
from flask import Flask, jsonify, request, send_from_directory
from faster_whisper import WhisperModel
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from werkzeug.utils import secure_filename


PROJECT_DIR = Path(__file__).resolve().parent
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".flac"}
MAX_AUDIO_SIZE = 50 * 1024 * 1024
MAX_TRANSCRIPT_LENGTH = 60_000

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "240"))

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_AUDIO_SIZE
app.json.ensure_ascii = False

_whisper_model: WhisperModel | None = None
_whisper_lock = threading.Lock()
_clinical_nlp: Any | None = None
_clinical_nlp_lock = threading.Lock()


class MedicalNote(BaseModel):
    """Contrat strict entre Ollama, Flask et l'interface HTML."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    motif_consultation: str = Field(
        description="Raison principale de la consultation avec durée si elle est mentionnée."
    )
    symptomes: str = Field(
        description="Symptômes confirmés, caractéristiques, intensité, durée et facteurs associés."
    )
    antecedents_traitements: str = Field(
        description="Antécédents, allergies et traitements explicitement mentionnés."
    )
    examen_clinique: str = Field(
        description="Constatations de l'examen clinique explicitement prononcées."
    )
    diagnostic_evoque: str = Field(
        description="Diagnostic ou hypothèse prudente, jamais présenté comme certain."
    )
    plan_recommandations: str = Field(
        description="Examens, traitement, conseils, suivi et signes d'alerte mentionnés."
    )

    @field_validator("*")
    @classmethod
    def replace_empty_values(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        return cleaned if cleaned else "Non renseigné dans la conversation."


class GenerateNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    transcript: str = Field(min_length=3, max_length=MAX_TRANSCRIPT_LENGTH)
    language: Literal["fr", "en"] = "fr"


class OllamaUnavailableError(RuntimeError):
    pass


class OllamaGenerationError(RuntimeError):
    pass


CLINICAL_TERMS: dict[str, list[str]] = {
    "SYMPTOME": [
        "douleur", "douleurs", "douleur abdominale", "douleurs abdominales",
        "douleur thoracique", "douleurs thoraciques", "crampe", "crampes",
        "nausée", "nausées", "vomissement", "vomissements", "diarrhée",
        "constipation", "ballonnement", "ballonnements", "fièvre", "toux",
        "fatigue", "vertige", "vertiges", "essoufflement",
        "difficulté à respirer", "mal de tête", "céphalée", "perte de poids",
        "perte d'appétit", "sang dans les selles", "palpitation", "palpitations", "insomnie",
        "nez bouché", "mal de gorge", "douleur musculaire",
    ],
    "DIAGNOSTIC": [
        "gastro-entérite", "trouble digestif fonctionnel", "syndrome de l'intestin irritable",
        "infection virale", "infection respiratoire", "bronchite", "grippe",
        "covid-19", "rhume", "angine", "migraine", "allergie", "diabète",
        "hypertension artérielle",
    ],
    "MEDICAMENT": [
        "paracétamol", "ibuprofène", "aspirine", "antibiotique", "antibiotiques", "amoxicilline",
        "antalgique", "anti-inflammatoire", "antispasmodique",
    ],
    "EXAMEN": [
        "analyse sanguine", "prise de sang", "échographie", "radiographie",
        "scanner", "irm", "examen clinique", "tension artérielle",
    ],
    "ANTECEDENT": [
        "allergie", "allergies", "maladie chronique", "antécédent", "antécédents", "chirurgie",
        "hospitalisation", "diabète", "hypertension",
    ],
}


def get_whisper_model() -> WhisperModel:
    """Charge Faster-Whisper une seule fois, lors de la première transcription."""
    global _whisper_model

    if _whisper_model is None:
        with _whisper_lock:
            if _whisper_model is None:
                _whisper_model = WhisperModel(
                    os.getenv("WHISPER_MODEL", "small"),
                    device=os.getenv("WHISPER_DEVICE", "cpu"),
                    compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
                )

    return _whisper_model


def get_clinical_nlp() -> Any:
    """Construit une pipeline EDS-NLP adaptée aux conversations cliniques françaises."""
    global _clinical_nlp

    if _clinical_nlp is None:
        with _clinical_nlp_lock:
            if _clinical_nlp is None:
                import edsnlp
                import edsnlp.pipes as eds

                pipeline = edsnlp.blank("eds")
                pipeline.add_pipe(eds.sentences())
                pipeline.add_pipe(
                    eds.matcher(
                        terms=CLINICAL_TERMS,
                        attr="LOWER",
                        term_matcher="exact",
                    )
                )
                pipeline.add_pipe(eds.negation())
                pipeline.add_pipe(eds.hypothesis())
                pipeline.add_pipe(eds.dates())
                _clinical_nlp = pipeline

    return _clinical_nlp


def analyze_with_edsnlp(transcript: str) -> dict[str, Any]:
    """Retourne des indices cliniques, sans rédiger ni diagnostiquer."""
    pipeline = get_clinical_nlp()
    with _clinical_nlp_lock:
        doc = pipeline(transcript)

    entities = []
    for entity in doc.ents:
        entities.append(
            {
                "text": entity.text,
                "label": entity.label_,
                "negated": bool(getattr(entity._, "negation", False)),
                "hypothetical": bool(getattr(entity._, "hypothesis", False)),
            }
        )

    durations = [span.text for span in doc.spans.get("durations", [])]
    dates = [span.text for span in doc.spans.get("dates", [])]

    return {
        "entities": entities,
        "durations": list(dict.fromkeys(durations)),
        "dates": list(dict.fromkeys(dates)),
    }


SYSTEM_PROMPT_FR = """
Tu es un assistant de documentation clinique destiné uniquement aux professionnels de santé.
Transforme une transcription de consultation en brouillon de note médicale structurée.

Règles obligatoires :
- Utilise uniquement les informations présentes dans la transcription.
- N'invente jamais un examen, une mesure, un antécédent, une allergie, un médicament ou une prescription.
- Distingue les symptômes confirmés des questions du médecin et des symptômes niés.
- Respecte les négations et les hypothèses signalées par EDS-NLP.
- Ne recopie pas la conversation et ne mentionne pas les salutations.
- Rédige des paragraphes médicaux courts, précis et professionnels.
- Si une rubrique n'est pas documentée, écris exactement : "Non renseigné dans la conversation."
- Un diagnostic explicitement prononcé doit être qualifié selon le contexte.
- Si aucun diagnostic n'est prononcé mais qu'une hypothèse clinique simple est fortement suggérée,
  écris "Hypothèse possible : ... — à confirmer par le médecin et les examens nécessaires."
- Ne présente jamais une hypothèse comme un diagnostic certain.
- Les recommandations doivent provenir de la conversation ; n'ajoute aucun dosage.
- La sortie doit respecter exactement le schéma JSON fourni, sans texte supplémentaire.
""".strip()


SYSTEM_PROMPT_EN = """
You are a clinical documentation assistant intended only for healthcare professionals.
Transform the consultation transcript into a concise structured draft note.
Use only stated information, respect negations and uncertainty, never invent findings,
medications, doses, tests, or history, and never present a hypothesis as certain.
If a section is undocumented, write exactly: "Not provided in the conversation."
Return only data matching the supplied JSON schema.
""".strip()


def generate_note_with_ollama(
    transcript: str,
    clinical_signals: dict[str, Any],
    language: Literal["fr", "en"],
) -> MedicalNote:
    schema = MedicalNote.model_json_schema()
    prompt = (
        "TRANSCRIPTION DE LA CONSULTATION :\n"
        f"{transcript}\n\n"
        "SIGNAUX EDS-NLP (aide à l'extraction, à vérifier contre la transcription) :\n"
        f"{json.dumps(clinical_signals, ensure_ascii=False, indent=2)}"
    )

    payload = {
        "model": OLLAMA_MODEL,
        "system": SYSTEM_PROMPT_EN if language == "en" else SYSTEM_PROMPT_FR,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": schema,
        "keep_alive": "10m",
        "options": {
            "temperature": 0.1,
            "seed": 42,
        },
    }

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
    except requests.ConnectionError as error:
        raise OllamaUnavailableError(
            "Ollama n'est pas accessible. Lancez Ollama puis vérifiez le modèle "
            f"{OLLAMA_MODEL}."
        ) from error
    except requests.Timeout as error:
        raise OllamaGenerationError(
            "Ollama a dépassé le délai de génération. Réessayez ou utilisez un modèle plus léger."
        ) from error
    except requests.RequestException as error:
        details = ""
        if error.response is not None:
            try:
                details = error.response.json().get("error", "")
            except ValueError:
                details = error.response.text[:300]
        raise OllamaGenerationError(details or "La génération Ollama a échoué.") from error

    try:
        content = response.json()["response"]
        return MedicalNote.model_validate_json(content)
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        raise OllamaGenerationError(
            "La réponse du modèle ne respecte pas le schéma médical attendu."
        ) from error


def ollama_health() -> dict[str, Any]:
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        response.raise_for_status()
        models = [item.get("name", "") for item in response.json().get("models", [])]
        model_ready = any(
            name == OLLAMA_MODEL
            or (
                ":" not in OLLAMA_MODEL
                and name.split(":", 1)[0] == OLLAMA_MODEL
            )
            for name in models
        )
        return {"status": "ok", "model": OLLAMA_MODEL, "model_ready": model_ready}
    except requests.RequestException:
        return {"status": "unavailable", "model": OLLAMA_MODEL, "model_ready": False}


@app.get("/")
def index():
    return send_from_directory(PROJECT_DIR, "index.html")


@app.get("/<path:filename>")
def static_files(filename: str):
    return send_from_directory(PROJECT_DIR, filename)


@app.get("/api/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "transcription": "faster-whisper",
            "clinical_nlp": "edsnlp",
            "validation": "pydantic",
            "ollama": ollama_health(),
        }
    )


@app.post("/api/transcribe")
def transcribe_audio():
    audio = request.files.get("audio")

    if audio is None or not audio.filename:
        return jsonify({"error": "Aucun fichier audio reçu."}), 400

    safe_name = secure_filename(audio.filename)
    suffix = Path(safe_name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        return jsonify(
            {"error": "Format non accepté. Utilisez MP3, WAV, M4A, MP4, WEBM, OGG ou FLAC."}
        ), 415

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

        return jsonify(
            {
                "text": text,
                "language": info.language,
                "language_probability": round(float(info.language_probability), 4),
                "duration": round(float(info.duration), 2),
            }
        )
    except Exception as error:
        app.logger.exception("Whisper transcription failed")
        return jsonify(
            {
                "error": "Impossible de transcrire ce fichier. Vérifiez l'audio puis réessayez.",
                "details": str(error),
            }
        ), 500


@app.post("/api/generate-note")
def generate_medical_note():
    try:
        payload = GenerateNoteRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as error:
        return jsonify(
            {
                "error": "La transcription est vide ou invalide.",
                "details": error.errors(include_url=False),
            }
        ), 400

    try:
        clinical_signals = analyze_with_edsnlp(payload.transcript)
        note = generate_note_with_ollama(
            payload.transcript,
            clinical_signals,
            payload.language,
        )
        return jsonify(
            {
                "note": note.model_dump(),
                "analysis": clinical_signals,
                "model": OLLAMA_MODEL,
                "warning": "Brouillon généré automatiquement : validation médicale obligatoire.",
            }
        )
    except OllamaUnavailableError as error:
        return jsonify({"error": str(error), "code": "OLLAMA_UNAVAILABLE"}), 503
    except OllamaGenerationError as error:
        return jsonify({"error": str(error), "code": "OLLAMA_GENERATION_FAILED"}), 502
    except Exception as error:
        app.logger.exception("Medical note generation failed")
        return jsonify(
            {
                "error": "Impossible de générer la note médicale.",
                "details": str(error),
            }
        ), 500


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify({"error": "Le fichier dépasse la limite de 50 MB."}), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
