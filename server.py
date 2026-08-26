"""Serveur local MediNOTE AI.

Pipeline:
    Audio -> Gemini -> transcription
    Transcription -> Gemini -> JSON structuré
    JSON -> Pydantic -> note médicale à faire valider par le médecin

Les fichiers audio sont traités dans un dossier temporaire automatiquement
supprimé à la fin de chaque requête.
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Literal

from flask import Flask, jsonify, request, send_from_directory
from google import genai
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from dotenv import load_dotenv
from werkzeug.utils import secure_filename


PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".flac"}
MAX_AUDIO_SIZE = 50 * 1024 * 1024
MAX_TRANSCRIPT_LENGTH = 60_000
MAX_CHAT_MESSAGE_LENGTH = 4_000
MAX_CHAT_MESSAGES = 12

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_AUDIO_SIZE
app.json.ensure_ascii = False

_gemini_client: genai.Client | None = None
_gemini_lock = threading.Lock()


class MedicalNote(BaseModel):
    """Contrat strict entre Gemini, Flask et l'interface HTML."""

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


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Literal["user", "model"]
    content: str = Field(min_length=1, max_length=MAX_CHAT_MESSAGE_LENGTH)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_CHAT_MESSAGES)
    language: Literal["fr", "en"] = "fr"

    @field_validator("messages")
    @classmethod
    def require_last_user_message(cls, messages: list[ChatMessage]) -> list[ChatMessage]:
        if messages[-1].role != "user":
            raise ValueError("Le dernier message doit provenir de l'utilisateur.")
        return messages


CHAT_SYSTEM_PROMPT = """
Tu es l'assistant conversationnel médical de MediNOTE AI.

Objectif : fournir des informations générales, prudentes et compréhensibles sur la santé,
et aider l'utilisateur à préparer ses questions pour un professionnel de santé.

Règles obligatoires :
- Réponds dans la langue de l'utilisateur (français ou anglais).
- Ne prétends jamais être médecin et ne remplace jamais une consultation médicale.
- Ne pose pas de diagnostic certain et ne prescris aucun médicament ni dosage.
- Demande seulement les précisions utiles et évite de collecter des données identifiantes.
- Pour une urgence possible (douleur thoracique intense, difficulté respiratoire sévère,
  perte de connaissance, paralysie soudaine, saignement important, idées suicidaires ou
  autre danger immédiat), recommande clairement de contacter immédiatement les services
  d'urgence locaux. Au Maroc : 15 pour l'ambulance/protection civile ou 112 depuis un mobile.
- Reste concis, empathique et factuel.
- Termine les réponses médicales personnalisées par un rappel bref de consulter un
  professionnel de santé si les symptômes persistent, s'aggravent ou inquiètent.
""".strip()


def get_gemini_client() -> genai.Client:
    """Crée le client Gemini côté serveur sans exposer la clé au navigateur."""
    global _gemini_client

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY n'est pas configurée. Ajoutez une nouvelle clé dans le fichier .env."
        )

    if _gemini_client is None:
        with _gemini_lock:
            if _gemini_client is None:
                _gemini_client = genai.Client(api_key=GEMINI_API_KEY)

    return _gemini_client


def gemini_error_details(error: Exception) -> tuple[str, int, str]:
    """Convertit les erreurs des transports Gemini en message sûr pour l'interface."""
    raw_code = getattr(error, "code", None)
    try:
        status_code = int(raw_code)
    except (TypeError, ValueError):
        match = re.search(r"(?:Error code:|['\"]code['\"]\s*:)\s*(\d{3})", str(error))
        status_code = int(match.group(1)) if match else 0

    if status_code == 400:
        return (
            "La requête Gemini est refusée. Vérifiez la clé Google AI Studio et la configuration du modèle.",
            502,
            "GEMINI_BAD_REQUEST",
        )
    if status_code in {401, 403}:
        return (
            "La clé Gemini est invalide ou non autorisée. Remplacez-la dans le fichier .env.",
            503,
            "GEMINI_AUTH_ERROR",
        )
    if status_code == 404:
        return (
            f"Le modèle {GEMINI_MODEL} n'est pas disponible pour cette clé. "
            "Utilisez gemini-3.5-flash-lite dans le fichier .env.",
            502,
            "GEMINI_MODEL_UNAVAILABLE",
        )
    if status_code == 429:
        return (
            "La limite ou le crédit Gemini est atteint. Patientez ou vérifiez votre quota Google AI Studio.",
            429,
            "GEMINI_QUOTA_EXCEEDED",
        )
    return (
        "Le service Gemini est momentanément indisponible.",
        502,
        "GEMINI_API_ERROR",
    )


SYSTEM_PROMPT_FR = """
Tu es un assistant de documentation clinique destiné uniquement aux professionnels de santé.
Transforme une transcription de consultation en brouillon de note médicale structurée.

Règles obligatoires :
- Utilise uniquement les informations présentes dans la transcription.
- N'invente jamais un examen, une mesure, un antécédent, une allergie, un médicament ou une prescription.
- Distingue les symptômes confirmés des questions du médecin et des symptômes niés.
- Respecte strictement les négations, les questions et les hypothèses de la conversation.
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


def generate_note_with_gemini(
    transcript: str,
    language: Literal["fr", "en"],
) -> MedicalNote:
    prompt = (
        "TRANSCRIPTION DE LA CONSULTATION :\n"
        f"{transcript}"
    )

    client = get_gemini_client()
    response = client.interactions.create(
        model=GEMINI_MODEL,
        input=prompt,
        system_instruction=SYSTEM_PROMPT_EN if language == "en" else SYSTEM_PROMPT_FR,
        generation_config={
            "temperature": 0.1,
            "max_output_tokens": 1400,
        },
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": MedicalNote.model_json_schema(),
        },
        store=False,
    )

    try:
        return MedicalNote.model_validate_json(response.output_text)
    except (AttributeError, TypeError, ValueError, ValidationError) as error:
        raise ValueError(
            "Gemini a retourné une note qui ne respecte pas le schéma médical attendu."
        ) from error


def _file_state_name(remote_file: object) -> str:
    state = getattr(remote_file, "state", "")
    return str(getattr(state, "name", state)).upper()


def transcribe_with_gemini(
    audio_path: Path,
    language: Literal["fr", "en"] | None,
) -> str:
    """Téléverse temporairement l'audio, le transcrit, puis le supprime de Gemini."""
    client = get_gemini_client()
    remote_file = None
    language_instruction = (
        "La conversation est principalement en français."
        if language == "fr"
        else "The conversation is mainly in English."
        if language == "en"
        else "Détecte automatiquement la langue de la conversation."
    )
    prompt = f"""
Tu es un moteur de transcription médicale fidèle. {language_instruction}
Transcris intégralement cet enregistrement, sans résumé, diagnostic, correction médicale
ni information inventée. Conserve les nombres, médicaments, durées, symptômes et négations.
Sépare les prises de parole en paragraphes lorsque le changement d'interlocuteur est clair,
mais n'invente pas l'identité des personnes. Retourne uniquement la transcription en texte brut.
""".strip()

    try:
        remote_file = client.files.upload(file=str(audio_path))
        deadline = time.monotonic() + 90

        while _file_state_name(remote_file).endswith("PROCESSING"):
            if time.monotonic() >= deadline:
                raise TimeoutError("Gemini a dépassé le délai de préparation du fichier audio.")
            time.sleep(1)
            remote_file = client.files.get(name=remote_file.name)

        if _file_state_name(remote_file).endswith("FAILED"):
            raise ValueError("Gemini n'a pas pu préparer ce fichier audio.")

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt, remote_file],
            config={
                "temperature": 0,
                "max_output_tokens": 8192,
            },
        )
        transcript = (response.text or "").strip()
        if transcript.startswith("```") and transcript.endswith("```"):
            transcript = re.sub(r"^```(?:text)?\s*|\s*```$", "", transcript).strip()
        if not transcript:
            raise ValueError("Aucune parole n'a été détectée dans le fichier.")
        return transcript
    finally:
        if remote_file is not None and getattr(remote_file, "name", None):
            try:
                client.files.delete(name=remote_file.name)
            except Exception:
                app.logger.warning("Impossible de supprimer immédiatement le fichier Gemini temporaire.")


def gemini_health() -> dict[str, object]:
    return {
        "status": "configured" if GEMINI_API_KEY else "missing_key",
        "model": GEMINI_MODEL,
    }


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
            "transcription": "gemini",
            "medical_analysis": "gemini",
            "validation": "pydantic",
            "gemini": gemini_health(),
        }
    )


@app.post("/api/chat")
def medical_chat():
    try:
        payload = ChatRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as error:
        return jsonify(
            {
                "error": "Le message est vide ou invalide.",
                "details": error.errors(include_url=False, include_context=False),
            }
        ), 400

    role_names = {
        "user": "Utilisateur",
        "model": "Assistant",
    }
    conversation = "\n\n".join(
        f"{role_names[message.role]} : {message.content}"
        for message in payload.messages
    )
    interaction_input = (
        "Voici l'historique récent de la conversation. Réponds uniquement au dernier "
        "message de l'utilisateur en tenant compte du contexte :\n\n"
        f"{conversation}"
    )

    try:
        response = get_gemini_client().interactions.create(
            model=GEMINI_MODEL,
            input=interaction_input,
            system_instruction=CHAT_SYSTEM_PROMPT,
            generation_config={
                "temperature": 0.25,
                "max_output_tokens": 700,
            },
            store=False,
        )
        answer = (response.output_text or "").strip()
        if not answer:
            raise RuntimeError("Gemini n'a retourné aucune réponse.")
        return jsonify({"reply": answer, "model": GEMINI_MODEL})
    except RuntimeError as error:
        return jsonify({"error": str(error), "code": "GEMINI_NOT_CONFIGURED"}), 503
    except Exception as error:
        message, status, code = gemini_error_details(error)
        app.logger.exception("Gemini medical chat failed")
        return jsonify({"error": message, "code": code}), status


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
    language: Literal["fr", "en"] | None = (
        requested_language if requested_language in {"fr", "en"} else None
    )

    try:
        with tempfile.TemporaryDirectory(prefix="medinote-") as temp_dir:
            audio_path = Path(temp_dir) / (safe_name or f"consultation{suffix}")
            audio.save(audio_path)
            text = transcribe_with_gemini(audio_path, language)

        return jsonify(
            {
                "text": text,
                "language": language or "auto",
                "model": GEMINI_MODEL,
            }
        )
    except RuntimeError as error:
        return jsonify({"error": str(error), "code": "GEMINI_NOT_CONFIGURED"}), 503
    except (ValueError, TimeoutError) as error:
        return jsonify({"error": str(error), "code": "GEMINI_TRANSCRIPTION_FAILED"}), 502
    except Exception as error:
        message, status, code = gemini_error_details(error)
        app.logger.exception("Gemini transcription failed")
        return jsonify({"error": message, "code": code}), status


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
        note = generate_note_with_gemini(
            payload.transcript,
            payload.language,
        )
        return jsonify(
            {
                "note": note.model_dump(),
                "model": GEMINI_MODEL,
                "warning": "Brouillon généré automatiquement : validation médicale obligatoire.",
            }
        )
    except RuntimeError as error:
        return jsonify({"error": str(error), "code": "GEMINI_NOT_CONFIGURED"}), 503
    except ValueError as error:
        return jsonify({"error": str(error), "code": "GEMINI_INVALID_RESPONSE"}), 502
    except Exception as error:
        message, status, code = gemini_error_details(error)
        app.logger.exception("Medical note generation failed")
        return jsonify({"error": message, "code": code}), status


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify({"error": "Le fichier dépasse la limite de 50 MB."}), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
