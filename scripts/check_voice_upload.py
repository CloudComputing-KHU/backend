from fastapi.testclient import TestClient

from app.main import app
from app.services.question_service import mock_answers
from app.services.storage_service import storage_service


def main() -> None:
    mock_answers.clear()
    client = TestClient(app)
    original_upload_voice = storage_service.upload_voice
    storage_service.upload_voice = lambda user_id, stored_filename, contents, content_type: (
        f"s3://mock-bucket/voices/{user_id}/{stored_filename}"
    )

    try:
        response = client.post(
            "/answers/health/voice",
            data={
                "user_id": "parent_001",
                "question_id": "q_health_today",
            },
            files={
                "file": ("reply.m4a", b"fake-audio-data", "audio/x-m4a"),
            },
        )
        response.raise_for_status()
        payload = response.json()

        print("status_code:", response.status_code)
        print("voice_upload_response:", payload)

        answers_response = client.get("/answers/health", params={"user_id": "parent_001"})
        answers_response.raise_for_status()
        print("answers_response:", answers_response.json())
    finally:
        storage_service.upload_voice = original_upload_voice


if __name__ == "__main__":
    main()
