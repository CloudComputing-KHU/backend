from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app
from app.services.auth_service import get_current_user
from app.services.question_service import mock_answers
from app.services.storage_service import storage_service

MOCK_USER = {"sub": "parent_001", "email": "test@test.com", "custom:role": "parent"}

app.dependency_overrides[get_current_user] = lambda: MOCK_USER

client = TestClient(app)


def setup_function() -> None:
    mock_answers.clear()
    storage_service.upload_voice = lambda user_id, stored_filename, contents, content_type: (
        f"s3://mock-bucket/voices/{user_id}/{stored_filename}"
    )


def test_submit_voice_answer_returns_voice_metadata() -> None:
    response = client.post(
        "/answers/health/voice",
        data={
            "question_id": "q_health_today",
        },
        files={
            "file": ("reply.m4a", b"fake-audio-data", "audio/x-m4a"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Voice uploaded"
    assert payload["voice_status"] == "uploaded"
    assert payload["original_filename"] == "reply.m4a"
    assert payload["stored_filename"].endswith(".m4a")
    assert payload["file_size"] == len(b"fake-audio-data")


def test_submit_voice_answer_rejects_invalid_extension() -> None:
    response = client.post(
        "/answers/health/voice",
        data={
            "question_id": "q_health_today",
        },
        files={
            "file": ("reply.txt", b"not-audio", "text/plain"),
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid extension"}
