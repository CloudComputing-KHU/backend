from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app
from app.services.auth_service import get_current_user
from app.services.question_service import InMemoryQuestionBackend, mock_answers, question_service

client = TestClient(app)

MOCK_USER = {"sub": "parent_001", "email": "test@test.com", "custom:role": "parent"}


class _Request:
    def __init__(self, question_id: str, answer: str) -> None:
        self.question_id = question_id
        self.answer_type = "choice"
        self.answer = answer


def setup_function() -> None:
    question_service.set_backend(InMemoryQuestionBackend())
    mock_answers.clear()
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER


def test_today_question_status_reflects_persisted_progress() -> None:
    question_service.save_answer("health", _Request("q_health_today", "네"), "parent_001")
    question_service.save_answer("meal", _Request("q_meal_today", "네"), "parent_001")

    response = client.get("/questions/status/today")

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == "parent_001"
    assert payload["health_answered"] is True
    assert payload["meal_answered"] is True
    assert payload["mood_answered"] is False
    assert payload["completed_count"] == 2
    assert payload["next_type"] == "mood"
    assert payload["all_answered"] is False
