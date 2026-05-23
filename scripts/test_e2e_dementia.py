"""
치매 분석 E2E 테스트 스크립트
- Cognito 로그인 → JWT 토큰 획득
- 음성 파일 업로드 (S3 실제 저장)
- 치매 분석 요청 (Transcribe + Lambda/OpenAI 실제 호출)
- 결과 폴링 및 출력

사용법:
  # 더미 무음 mp3로 테스트 (Transcribe가 빈 텍스트 반환 → 분석 건너뜀)
  python scripts/test_e2e_dementia.py

  # 실제 한국어 음성 파일로 테스트 (GPT 분석까지 동작)
  python scripts/test_e2e_dementia.py --audio path/to/recording.mp3

  # Cognito 계정 지정
  python scripts/test_e2e_dementia.py --email user@example.com --password MyPass123!

환경변수 (.env):
  COGNITO_USER_POOL_ID, COGNITO_APP_CLIENT_ID, AWS_ACCESS_KEY_ID,
  AWS_SECRET_ACCESS_KEY, AWS_REGION, S3_BUCKET_NAME, LLM_API_GATEWAY_URL
"""

import argparse
import json
import os
import struct
import sys
import time

import boto3
from dotenv import load_dotenv

load_dotenv()

# ── 설정 ──

BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_EMAIL = os.getenv("TEST_EMAIL", "test@example.com")
DEFAULT_PASSWORD = os.getenv("TEST_PASSWORD", "TestPass123!")


# ── 더미 mp3 생성 ──

def generate_silent_mp3(duration_ms: int = 1000) -> bytes:
    """
    MPEG-1 Layer 3, 128kbps, 44100Hz, mono 무음 프레임을 생성한다.
    실제 mp3 헤더 + 무음 데이터로 Transcribe가 인식할 수 있는 최소한의 mp3.
    """
    # MPEG1 Layer3 128kbps 44100Hz mono 프레임 헤더
    frame_header = b'\xff\xfb\x90\x00'
    # 각 프레임은 417 바이트 (128kbps, 44100Hz 기준)
    frame_size = 417
    frame_data = frame_header + b'\x00' * (frame_size - len(frame_header))

    # 44100Hz, 1152 samples/frame → ~26.12ms/frame
    frames_needed = max(1, int(duration_ms / 26.12))
    return frame_data * frames_needed


# ── Cognito 로그인 ──

def cognito_login(email: str, password: str) -> str:
    """Cognito에 로그인하여 id_token을 반환한다."""
    client = boto3.client(
        "cognito-idp",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
    )
    app_client_id = os.getenv("COGNITO_APP_CLIENT_ID")
    if not app_client_id:
        print("FAIL: COGNITO_APP_CLIENT_ID 환경변수가 설정되지 않았습니다.")
        sys.exit(1)

    try:
        resp = client.initiate_auth(
            ClientId=app_client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": email, "PASSWORD": password},
        )
        result = resp["AuthenticationResult"]
        print(f"  Cognito 로그인 성공 - expires_in={result['ExpiresIn']}s")
        return result["IdToken"]
    except client.exceptions.NotAuthorizedException:
        print("FAIL: 이메일 또는 비밀번호가 올바르지 않습니다.")
        sys.exit(1)
    except client.exceptions.UserNotConfirmedException:
        print("FAIL: 이메일 인증이 완료되지 않았습니다.")
        sys.exit(1)
    except Exception as exc:
        print(f"FAIL: Cognito 로그인 실패 - {exc}")
        sys.exit(1)


# ── HTTP 헬퍼 ──

def api_request(method: str, path: str, token: str, **kwargs):
    """requests 없이 urllib로 API 호출"""
    import urllib.request
    import urllib.error

    url = f"{BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {token}"}

    if "json_body" in kwargs:
        data = json.dumps(kwargs["json_body"]).encode("utf-8")
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
    elif "multipart" in kwargs:
        # multipart/form-data 수동 구성
        boundary = "----E2ETestBoundary"
        body_parts = []

        for key, value in kwargs["multipart"]["fields"].items():
            body_parts.append(f"--{boundary}\r\n".encode())
            body_parts.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
            body_parts.append(f"{value}\r\n".encode())

        fname, fdata, ftype = kwargs["multipart"]["file"]
        body_parts.append(f"--{boundary}\r\n".encode())
        body_parts.append(
            f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'.encode()
        )
        body_parts.append(f"Content-Type: {ftype}\r\n\r\n".encode())
        body_parts.append(fdata)
        body_parts.append(f"\r\n--{boundary}--\r\n".encode())

        data = b"".join(body_parts)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
    else:
        req = urllib.request.Request(url, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, {"error": body}


# ── 메인 테스트 ──

def main():
    parser = argparse.ArgumentParser(description="치매 분석 E2E 테스트")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="Cognito 계정 이메일")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Cognito 계정 비밀번호")
    parser.add_argument("--audio", default=None, help="테스트용 음성 파일 경로 (.mp3/.m4a/.wav)")
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  치매 분석 E2E 테스트 (실제 AWS 연동)")
    print("=" * 60)
    print()

    # ── 1. Cognito 로그인 ──
    print("[1/5] Cognito 로그인")
    token = cognito_login(args.email, args.password)
    print()

    # ── 2. 음성 파일 준비 ──
    print("[2/5] 음성 파일 준비")
    if args.audio:
        if not os.path.exists(args.audio):
            print(f"FAIL: 파일이 존재하지 않습니다 - {args.audio}")
            sys.exit(1)
        with open(args.audio, "rb") as f:
            audio_data = f.read()
        filename = os.path.basename(args.audio)
        ext = os.path.splitext(filename)[1].lower()
        content_type_map = {".mp3": "audio/mpeg", ".m4a": "audio/x-m4a", ".wav": "audio/wav"}
        content_type = content_type_map.get(ext, "audio/mpeg")
        print(f"  실제 파일 사용: {filename} ({len(audio_data)} bytes)")
    else:
        audio_data = generate_silent_mp3(2000)  # 2초 무음
        filename = "test_dummy.mp3"
        content_type = "audio/mpeg"
        print(f"  더미 무음 mp3 생성: {filename} ({len(audio_data)} bytes)")
    print()

    # ── 3. 음성 업로드 ──
    print("[3/5] 음성 업로드 (POST /answers/health/voice)")
    status, body = api_request(
        "POST", "/answers/health/voice", token,
        multipart={
            "fields": {"question_id": "q_health_today"},
            "file": (filename, audio_data, content_type),
        },
    )
    if status != 200:
        print(f"  FAIL: HTTP {status} - {body}")
        sys.exit(1)

    answer_id = body["answer_id"]
    voice_file_key = body.get("voice_file_key", "")
    print(f"  PASS: answer_id={answer_id}")
    print(f"        voice_file_key={voice_file_key}")
    print(f"        voice_url={body.get('voice_url', 'N/A')[:80]}...")
    print()

    # ── 4. 치매 분석 요청 ──
    print("[4/5] 치매 분석 요청 (POST /dementia/analyze)")
    status, body = api_request(
        "POST", "/dementia/analyze", token,
        json_body={"answer_id": answer_id},
    )
    if status != 200:
        print(f"  FAIL: HTTP {status} - {body}")
        sys.exit(1)

    analysis_id = body["analysis_id"]
    print(f"  PASS: analysis_id={analysis_id}, status={body['status']}")
    print()

    # ── 5. 결과 폴링 (최대 5분) ──
    print("[5/5] 분석 결과 대기 (최대 5분, 5초 간격)")
    max_wait = 300
    elapsed = 0
    result = None

    while elapsed < max_wait:
        time.sleep(5)
        elapsed += 5

        status, body = api_request("GET", f"/dementia/{analysis_id}", token)
        if status != 200:
            print(f"  FAIL: HTTP {status} - {body}")
            sys.exit(1)

        current_status = body.get("status", "unknown")
        if elapsed % 15 == 0 or current_status in ("completed", "failed"):
            print(f"  [{elapsed}s] status={current_status}")

        if current_status == "completed":
            result = body
            break
        elif current_status == "failed":
            print(f"  FAIL: 분석 실패")
            print(f"  {json.dumps(body, ensure_ascii=False, indent=2)}")
            sys.exit(1)

    if result is None:
        print("  FAIL: 타임아웃 (5분 초과)")
        sys.exit(1)

    # ── 결과 출력 ──
    print()
    print("=" * 60)
    print("  분석 완료!")
    print("=" * 60)
    print(f"  analysis_id : {result.get('analysis_id')}")
    print(f"  status      : {result.get('status')}")
    print(f"  transcript  : {(result.get('transcript') or '')[:100]}...")
    print(f"  risk_level  : {result.get('risk_level')}")
    print(f"  risk_score  : {result.get('risk_score')}")
    print(f"  summary     : {result.get('analysis_summary')}")
    print(f"  indicators  : {result.get('indicators')}")
    print(f"  created_at  : {result.get('created_at')}")
    print(f"  completed_at: {result.get('completed_at')}")
    print()

    if result.get("risk_level") == "low" and result.get("risk_score") == 0.0:
        print("  ℹ️  더미 무음 파일이라 빈 발화로 처리됨 (정상)")
        print("     실제 한국어 음성으로 테스트하려면:")
        print("     python scripts/test_e2e_dementia.py --audio 내녹음.mp3")
    else:
        print("  ✅ GPT 분석 결과가 반환됨!")

    print()
    print("==> E2E TEST PASSED")


if __name__ == "__main__":
    main()
