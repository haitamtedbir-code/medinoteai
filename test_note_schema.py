"""Test local du contrat Pydantic, sans Whisper, EDS-NLP ni Ollama."""

from server import MedicalNote


def test_medical_note_schema() -> None:
    note = MedicalNote.model_validate(
        {
            "motif_consultation": "Douleurs abdominales depuis une semaine.",
            "symptomes": "Crampes abdominales, nausées et diarrhée.",
            "antecedents_traitements": "Prise occasionnelle de paracétamol.",
            "examen_clinique": "Non renseigné dans la conversation.",
            "diagnostic_evoque": "Hypothèse possible : trouble digestif fonctionnel — à confirmer.",
            "plan_recommandations": "Analyse sanguine et suivi médical mentionnés.",
        }
    )
    assert note.motif_consultation.startswith("Douleurs abdominales")
    assert "diarrhée" in note.symptomes


if __name__ == "__main__":
    test_medical_note_schema()
    print("Schéma Pydantic : OK")
