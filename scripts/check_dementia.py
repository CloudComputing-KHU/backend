"""
치매 분석 파이프라인 스모크 테스트 스크립트
- 음성 업로드 → 치매 분석 요청 → 결과 폴링까지 테스트
- S3 mock을 사용하므로 실제 AWS 호출은 하지 않음 (로컬 검증용)
"""

import time
from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_service import get_current_user
from app.services.question_service import mock_answers
from app.services.dementia_service import mock_analyses, dementia_service
from app.services.storage_service import storage_service


def main() -> None:
    mock_answers.clear()
    mock_analyses.clear()

    # Auth mock
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "parent_001",
        "email": "test@test.com",
        "custom:role": "parent",
    }

    client = TestClient(app)

    # S3 및 Presigned URL mock
    original_upload_voice = storage_service.upload_voice
    storage_service.upload_voice = lambda user_id, stored_filename, contents, content_type: (
        f"s3://mock-bucket/voices/{user_id}/{stored_filename}"
    )
    original_generate_presigned_url = storage_service.generate_presigned_url
    storage_service.generate_presigned_url = lambda s3_uri, expiration=604800: (
        f"https://mock-bucket.s3.amazonaws.com/{s3_uri.split('s3://')[-1]}"
    )

    # Whisper STT 및 LLM 분석 mock
    original_speech_to_text = dementia_service._speech_to_text_whisper
    dementia_service._speech_to_text_whisper = lambda analysis_id, key: (
        "오늘 아침에... 약을 먹었는지 기억이 잘 안 나요. 밥은 먹었나? 여기가 어디지?"
    )

    original_analyze_with_llm = dementia_service._analyze_with_llm
    dementia_service._analyze_with_llm = lambda analysis_id, transcript: {
        "risk_level": "medium",
        "risk_score": 0.4,
        "analysis_summary": "약간의 단기 기억 감퇴 조짐이 보입니다.",
        "indicators": ["short_term_memory_loss"]
    }

    try:
        # 1. 음성 답변 업로드
        print("=" * 60)
        print("[1단계] 음성 답변 업로드")
        print("=" * 60)

        voice_response = client.post(
            "/answers/health/voice",
            data={
                "user_id": "parent_001",
                "question_id": "q_health_today",
            },
            files={
                "file": ("reply.m4a", b"fake-audio-data", "audio/x-m4a"),
            },
        )
        voice_response.raise_for_status()
        voice_payload = voice_response.json()
        print("status_code:", voice_response.status_code)
        print("voice_upload_response:", voice_payload)

        answer_id = voice_payload["answer_id"]

        # 2. 치매 분석 요청
        print()
        print("=" * 60)
        print("[2단계] 치매 분석 요청")
        print("=" * 60)

        analysis_response = client.post(
            "/dementia/analyze",
            json={
                "user_id": "parent_001",
                "answer_id": answer_id,
            },
        )
        analysis_response.raise_for_status()
        analysis_payload = analysis_response.json()
        print("status_code:", analysis_response.status_code)
        print("analysis_response:", analysis_payload)

        analysis_id = analysis_payload["analysis_id"]

        # 3. 분석 결과 조회
        print()
        print("=" * 60)
        print("[3단계] 분석 결과 조회")
        print("=" * 60)

        result_response = client.get(f"/dementia/{analysis_id}")
        result_response.raise_for_status()
        result_payload = result_response.json()
        print("status_code:", result_response.status_code)
        print("analysis_result:", result_payload)

        # 4. 사용자별 분석 이력 조회
        print()
        print("=" * 60)
        print("[4단계] 사용자별 분석 이력 조회")
        print("=" * 60)

        history_response = client.get("/dementia", params={"user_id": "parent_001"})
        history_response.raise_for_status()
        print("status_code:", history_response.status_code)
        print("analysis_history:", history_response.json())

        # 5. 비음성 답변 분석 거부 테스트
        print()
        print("=" * 60)
        print("[5단계] 비음성 답변 분석 거부 테스트")
        print("=" * 60)

        text_response = client.post(
            "/answers/health",
            json={
                "user_id": "parent_001",
                "question_id": "q_health_today",
                "answer_type": "choice",
                "answer": "네, 먹었어요",
            },
        )
        text_response.raise_for_status()

        # 텍스트 답변의 answer_id를 찾아서 분석 요청
        answers_list = client.get("/answers/health", params={"user_id": "parent_001"}).json()
        text_answer = next(a for a in answers_list if a["answer_type"] == "choice")

        reject_response = client.post(
            "/dementia/analyze",
            json={
                "user_id": "parent_001",
                "answer_id": text_answer["answer_id"],
            },
        )
        print("status_code:", reject_response.status_code)
        print("reject_response:", reject_response.json())
        assert reject_response.status_code == 400, "비음성 답변은 400이어야 합니다"

        print()
        print("=" * 60)
        print("[OK] dementia analysis smoke check completed")
        print("=" * 60)

    finally:
        storage_service.upload_voice = original_upload_voice
        storage_service.generate_presigned_url = original_generate_presigned_url
        dementia_service._speech_to_text_whisper = original_speech_to_text
        dementia_service._analyze_with_llm = original_analyze_with_llm
        app.dependency_overrides.clear()


if __name__ == "__main__":
    main()
