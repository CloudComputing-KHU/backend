import io
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

from fastapi.testclient import TestClient
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app
from app.services.auth_service import get_current_user
from app.services.dementia_service import InMemoryDementiaBackend, dementia_service, mock_analyses
from app.services.family_service import InMemoryFamilyBackend, family_service, mock_family_invites, mock_family_links
from app.services.notification_service import InMemoryNotificationBackend, notification_service
from app.services.photo_service import InMemoryPhotoBackend, mock_photos, photo_service
from app.services.question_service import InMemoryQuestionBackend, mock_answers, question_service
from app.services.storage_service import storage_service

client = TestClient(app)

CHILD_USER = {
    "sub": "child_001",
    "email": "child@test.com",
    "custom:role": "child",
}
PARENT_USER = {
    "sub": "parent_001",
    "email": "parent@test.com",
    "custom:role": "parent",
}


def _link_family() -> None:
    mock_family_links.append(
        {
            "link_id": "link_test1234",
            "parent_user_id": "parent_001",
            "child_user_id": "child_001",
            "status": "active",
            "created_at": None,
            "connected_at": None,
        }
    )


def _png_bytes() -> bytes:
    image = Image.new("RGB", (4, 4), color=(255, 120, 0))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def setup_function() -> None:
    app.dependency_overrides.clear()
    family_service.set_backend(InMemoryFamilyBackend())
    question_service.set_backend(InMemoryQuestionBackend())
    photo_service.set_backend(InMemoryPhotoBackend())
    dementia_service.set_backend(InMemoryDementiaBackend())
    notification_service.set_backend(InMemoryNotificationBackend())
    mock_family_invites.clear()
    mock_family_links.clear()
    mock_answers.clear()
    mock_analyses.clear()
    mock_photos.clear()
    storage_service.upload_photo = lambda user_id, stored_filename, contents, content_type: (
        f"s3://mock-bucket/photos/{user_id}/{stored_filename}"
    )
    notification_service.send = lambda user_id, title, body, data=None: True


def test_child_reads_linked_parent_answers() -> None:
    _link_family()
    mock_answers.append(
        {
            "answer_id": "answer_parent_1",
            "type": "health",
            "user_id": "parent_001",
            "question_id": "q_health_today",
            "answer_type": "choice",
            "answer": "네, 먹었어요",
            "voice_status": None,
            "voice_file_key": None,
            "original_filename": None,
            "stored_filename": None,
            "content_type": None,
            "file_size": None,
            "created_at": datetime.now(),
        }
    )
    app.dependency_overrides[get_current_user] = lambda: CHILD_USER

    response = client.get("/answers/health")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["user_id"] == "parent_001"
    assert payload[0]["answer"] == "네, 먹었어요"


def test_child_reads_linked_parent_dementia_history_and_detail() -> None:
    _link_family()
    mock_analyses.append(
        {
            "analysis_id": "analysis_parent_1",
            "answer_id": "answer_voice_1",
            "user_id": "parent_001",
            "status": "completed",
            "transcript": "안녕하세요",
            "risk_level": "low",
            "risk_score": 0.1,
            "analysis_summary": "위험도 낮음",
            "indicators": [],
            "created_at": datetime.now(),
            "completed_at": datetime.now(),
        }
    )
    app.dependency_overrides[get_current_user] = lambda: CHILD_USER

    history_response = client.get("/dementia")
    detail_response = client.get("/dementia/analysis_parent_1")

    assert history_response.status_code == 200
    assert history_response.json()[0]["user_id"] == "parent_001"
    assert detail_response.status_code == 200
    assert detail_response.json()["analysis_id"] == "analysis_parent_1"


def test_child_photo_upload_uses_linked_parent_as_receiver() -> None:
    _link_family()
    app.dependency_overrides[get_current_user] = lambda: CHILD_USER

    response = client.post(
        "/photos",
        data={},
        files={
            "file": ("photo.png", _png_bytes(), "image/png"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sender_user_id"] == "child_001"
    assert payload["receiver_user_id"] == "parent_001"


def test_past_scheduled_photo_is_sent_immediately() -> None:
    _link_family()
    app.dependency_overrides[get_current_user] = lambda: CHILD_USER

    response = client.post(
        "/photos",
        data={
            "scheduled_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        },
        files={
            "file": ("photo.png", _png_bytes(), "image/png"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "sent"
    assert payload["scheduled_at"] is None

    app.dependency_overrides[get_current_user] = lambda: PARENT_USER
    received_response = client.get("/photos/received")

    assert received_response.status_code == 200
    received_payload = received_response.json()
    assert len(received_payload) == 1
    assert received_payload[0]["receiver_user_id"] == "parent_001"


def test_child_relation_required_for_parent_data_routes() -> None:
    app.dependency_overrides[get_current_user] = lambda: CHILD_USER

    answers_response = client.get("/answers/health")
    dementia_response = client.get("/dementia")
    photo_response = client.post(
        "/photos",
        data={},
        files={"file": ("photo.png", _png_bytes(), "image/png")},
    )

    assert answers_response.status_code == 409
    assert dementia_response.status_code == 409
    assert photo_response.status_code == 409
