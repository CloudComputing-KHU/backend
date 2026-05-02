"""
Lambda + API Gateway 연동 테스트 (S3/Transcribe 제외)
- S3 업로드를 mock 처리
- Transcribe STT를 mock 처리 (가짜 한국어 발화 텍스트 반환)
- Lambda(OpenAI) API Gateway 호출만 실제로 테스트

이 스크립트는 .env에 LLM_API_GATEWAY_URL이 설정되어 있어야 합니다.
"""

import json
import os
import sys
import urllib.request
import urllib.error

from dotenv import load_dotenv

load_dotenv()


def test_1_api_gateway_direct():
    """1단계: API Gateway + Lambda를 직접 호출하여 OpenAI 연동 확인"""
    print("=" * 60)
    print("[1] API Gateway + Lambda 직접 호출 테스트")
    print("=" * 60)

    url = os.getenv("LLM_API_GATEWAY_URL")
    if not url:
        print("FAIL: LLM_API_GATEWAY_URL 환경변수가 설정되지 않았습니다.")
        return False

    print(f"URL: {url}")

    # 치매 위험 지표가 있는 샘플 발화
    sample_transcript = (
        "오늘 아침에... 그거... 뭐였더라... 약을 먹었는데... "
        "그거 있잖아, 그... 아 기억이 안 나요. "
        "아까 뭐 했더라... 밥은 먹었나? 밥은 먹었나? "
        "여기가 어디지... 병원인가? 집인가?"
    )

    payload = json.dumps({"transcript": sample_transcript}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        print("요청 전송 중... (최대 2분 대기)")
        with urllib.request.urlopen(req, timeout=120) as resp:
            status = resp.status
            body = json.loads(resp.read().decode("utf-8"))

        print(f"HTTP Status: {status}")
        print(f"Raw Response: {json.dumps(body, ensure_ascii=False, indent=2)}")

        # API Gateway proxy 형식 처리
        if isinstance(body, dict) and "body" in body:
            result = json.loads(body["body"]) if isinstance(body["body"], str) else body["body"]
        else:
            result = body

        # 결과 검증
        if "error" in result:
            print(f"FAIL: Lambda 에러 응답 - {result['error']}")
            return False

        required_fields = ["risk_level", "risk_score", "analysis_summary", "indicators"]
        missing = [f for f in required_fields if f not in result]
        if missing:
            print(f"FAIL: 응답에 필수 필드 누락 - {missing}")
            return False

        print()
        print("--- 분석 결과 ---")
        print(f"  risk_level: {result['risk_level']}")
        print(f"  risk_score: {result['risk_score']}")
        print(f"  summary: {result['analysis_summary']}")
        print(f"  indicators: {result['indicators']}")
        print()
        print("PASS: API Gateway + Lambda + OpenAI 연동 정상!")
        return True

    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(f"FAIL: HTTP {exc.code} - {error_body}")
        return False
    except urllib.error.URLError as exc:
        print(f"FAIL: 연결 실패 - {exc}")
        return False
    except Exception as exc:
        print(f"FAIL: 예외 발생 - {exc}")
        return False


def test_2_fastapi_with_mocks():
    """2단계: FastAPI 엔드포인트 + S3/Transcribe mock + 실제 Lambda 호출"""
    print()
    print("=" * 60)
    print("[2] FastAPI 엔드포인트 통합 테스트 (S3/Transcribe mock)")
    print("=" * 60)

    # FastAPI 앱 import
    sys.path.insert(0, ".")
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.question_service import mock_answers
    from app.services.dementia_service import mock_analyses, dementia_service
    from app.services.storage_service import storage_service

    mock_answers.clear()
    mock_analyses.clear()

    # S3 업로드 mock
    original_upload = storage_service.upload_voice
    storage_service.upload_voice = lambda user_id, stored_filename, contents, content_type: (
        f"s3://mock-bucket/voices/{user_id}/{stored_filename}"
    )

    # Transcribe mock - STT를 건너뛰고 가짜 텍스트 반환
    sample_transcript = (
        "오늘 아침에... 그거... 뭐였더라... 약을 먹었는데... "
        "그거 있잖아, 그... 아 기억이 안 나요. "
        "아까 뭐 했더라... 밥은 먹었나? 밥은 먹었나? "
        "여기가 어디지... 병원인가? 집인가?"
    )

    original_start = dementia_service._start_transcription
    original_wait = dementia_service._wait_for_transcription

    dementia_service._start_transcription = lambda record, key: "mock-job-name"
    dementia_service._wait_for_transcription = lambda job, record: sample_transcript

    client = TestClient(app)

    try:
        # 2-1. 음성 업로드
        print()
        print("[2-1] 음성 답변 업로드")
        resp = client.post(
            "/answers/health/voice",
            data={"user_id": "parent_001", "question_id": "q_health_today"},
            files={"file": ("test.m4a", b"fake-audio", "audio/x-m4a")},
        )
        assert resp.status_code == 200, f"음성 업로드 실패: {resp.status_code}"
        answer_id = resp.json()["answer_id"]
        print(f"  PASS: answer_id={answer_id}")

        # 2-2. 치매 분석 요청
        print("[2-2] 치매 분석 요청")
        resp = client.post(
            "/dementia/analyze",
            json={"user_id": "parent_001", "answer_id": answer_id},
        )
        assert resp.status_code == 200, f"분석 요청 실패: {resp.status_code}"
        analysis_id = resp.json()["analysis_id"]
        status = resp.json()["status"]
        print(f"  PASS: analysis_id={analysis_id}, status={status}")

        # 2-3. 백그라운드 처리 대기 (TestClient에서는 동기 실행)
        import time
        print("[2-3] 백그라운드 처리 대기 (최대 30초)...")
        for i in range(30):
            time.sleep(1)
            resp = client.get(f"/dementia/{analysis_id}")
            result = resp.json()
            current_status = result["status"]
            if current_status in ("completed", "failed"):
                break
            if i % 5 == 0:
                print(f"  ... status={current_status} ({i+1}s)")

        # 2-4. 결과 확인
        print(f"[2-4] 최종 결과 확인")
        print(f"  status: {result['status']}")

        if result["status"] == "completed":
            print(f"  transcript: {result.get('transcript', '')[:80]}...")
            print(f"  risk_level: {result.get('risk_level')}")
            print(f"  risk_score: {result.get('risk_score')}")
            print(f"  summary: {result.get('analysis_summary')}")
            print(f"  indicators: {result.get('indicators')}")
            print()
            print("  PASS: FastAPI 파이프라인 (mock STT + 실제 Lambda) 정상!")
            return True
        else:
            print(f"  FAIL: 분석 실패 - status={result['status']}")
            return False

        # 2-5. 이력 조회
        print("[2-5] 이력 조회")
        resp = client.get("/dementia", params={"user_id": "parent_001"})
        assert resp.status_code == 200
        print(f"  PASS: 이력 {len(resp.json())}건 조회됨")

        # 2-6. 비음성 거부 테스트
        print("[2-6] 비음성 답변 거부 테스트")
        client.post("/answers/health", json={
            "user_id": "parent_001",
            "question_id": "q_health_today",
            "answer_type": "choice",
            "answer": "test",
        })
        answers = client.get("/answers/health", params={"user_id": "parent_001"}).json()
        text_ans = next(a for a in answers if a["answer_type"] == "choice")
        resp = client.post("/dementia/analyze", json={
            "user_id": "parent_001",
            "answer_id": text_ans["answer_id"],
        })
        assert resp.status_code == 400, f"비음성 거부 실패: {resp.status_code}"
        print(f"  PASS: 비음성 답변 정상 거부 (400)")

        return True

    except Exception as exc:
        print(f"  FAIL: 예외 발생 - {exc}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        storage_service.upload_voice = original_upload
        dementia_service._start_transcription = original_start
        dementia_service._wait_for_transcription = original_wait


def main():
    print()
    print("###################################################")
    print("#  Lambda + API Gateway 연동 테스트 (S3 제외)       #")
    print("###################################################")
    print()

    results = {}

    # 테스트 1: API Gateway 직접 호출
    results["api_gateway_direct"] = test_1_api_gateway_direct()

    # 테스트 2: FastAPI 통합 (mock STT + 실제 Lambda)
    results["fastapi_integration"] = test_2_fastapi_with_mocks()

    # 최종 요약
    print()
    print("=" * 60)
    print("최종 결과 요약")
    print("=" * 60)
    all_pass = True
    for name, passed in results.items():
        status_str = "PASS" if passed else "FAIL"
        print(f"  [{status_str}] {name}")
        if not passed:
            all_pass = False

    print()
    if all_pass:
        print("==> ALL TESTS PASSED")
    else:
        print("==> SOME TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
