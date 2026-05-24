"""
E2E 치매 위험 분석 통합 테스트 스크립트
실제 로그인 ➔ 실제 음성 업로드 ➔ 실제 치매 분석 시작 ➔ 결과 폴링 대기 ➔ 최종 결과 리포트 출력
"""

import argparse
import os
import sys
import time
from pathlib import Path
from fastapi.testclient import TestClient

# 프로젝트 루트를 시스템 경로에 추가
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app


def parse_args():
    parser = argparse.ArgumentParser(description="E2E 치매 위험 분석 연동 테스트")
    parser.add_argument("--email", required=True, help="AWS Cognito 로그인용 이메일 계정")
    parser.add_argument("--password", required=True, help="AWS Cognito 로그인용 비밀번호")
    parser.add_argument("--audio", required=True, help="로컬 오디오 파일 경로 (mp3, wav, m4a)")
    return parser.parse_args()


def main():
    args = parse_args()
    
    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"❌ 에러: 지정된 오디오 파일을 찾을 수 없습니다: {args.audio}")
        sys.exit(1)
        
    print("=" * 60)
    print("🚀 E2E 치매 위험 분석 통합 테스트 시작")
    print("=" * 60)

    client = TestClient(app)
    
    # 1단계: 로그인 시도
    print("\n🔑 [1단계] AWS Cognito 로그인 요청 중...")
    try:
        login_resp = client.post(
            "/auth/login",
            json={"email": args.email, "password": args.password}
        )
        if login_resp.status_code != 200:
            print(f"❌ 로그인 실패 (HTTP {login_resp.status_code}): {login_resp.text}")
            print("💡 .env의 COGNITO_APP_CLIENT_ID / COGNITO_USER_POOL_ID 설정을 확인하거나 회원가입 여부를 검증하세요.")
            sys.exit(1)
            
        login_data = login_resp.json()
        id_token = login_data.get("id_token")
        if not id_token:
            print("❌ 에러: 로그인 응답에 id_token이 존재하지 않습니다.")
            sys.exit(1)
            
        print("✅ 로그인 성공! 유효 토큰을 획득했습니다.")
    except Exception as exc:
        print(f"❌ 로그인 요청 중 예외 발생: {exc}")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {id_token}"}

    # 2단계: 음성 파일 업로드
    print(f"\n🎙️ [2단계] 음성 답변 업로드 중 (파일: {audio_path.name})...")
    
    # 확장자에 따른 MIME 타입 추정
    ext = audio_path.suffix.lower()
    content_type_map = {
        ".mp3": "audio/mp3",
        ".wav": "audio/wav",
        ".m4a": "audio/x-m4a"
    }
    content_type = content_type_map.get(ext, "audio/mpeg")
    
    try:
        with open(audio_path, "rb") as f:
            file_data = f.read()
            
        upload_resp = client.post(
            "/answers/health/voice",
            headers=headers,
            data={"question_id": "q_health_today"},
            files={"file": (audio_path.name, file_data, content_type)}
        )
        
        if upload_resp.status_code != 200:
            print(f"❌ 음성 업로드 실패 (HTTP {upload_resp.status_code}): {upload_resp.text}")
            sys.exit(1)
            
        upload_data = upload_resp.json()
        answer_id = upload_data.get("answer_id")
        voice_file_key = upload_data.get("voice_file_key")
        print(f"✅ 음성 업로드 완료! (answer_id: {answer_id})")
        print(f"🔗 S3 Key: {voice_file_key}")
    except Exception as exc:
        print(f"❌ 음성 업로드 중 예외 발생: {exc}")
        sys.exit(1)

    # 3단계: 치매 분석 요청
    print("\n🧠 [3단계] 치매 위험도 분석 요청 중...")
    try:
        analyze_resp = client.post(
            "/dementia/analyze",
            headers=headers,
            json={"answer_id": answer_id}
        )
        
        if analyze_resp.status_code != 200:
            print(f"❌ 치매 분석 요청 실패 (HTTP {analyze_resp.status_code}): {analyze_resp.text}")
            sys.exit(1)
            
        analyze_data = analyze_resp.json()
        analysis_id = analyze_data.get("analysis_id")
        status = analyze_data.get("status")
        print(f"✅ 분석 요청 성공! (analysis_id: {analysis_id}, 현재 상태: {status})")
    except Exception as exc:
        print(f"❌ 분석 요청 중 예외 발생: {exc}")
        sys.exit(1)

    # 4단계: 분석 결과 상태 폴링 및 대기
    print("\n⏳ [4단계] 치매 분석 작업 대기 및 폴링 시작 (최대 5분)...")
    max_retries = 60  # 5초 간격으로 60번 = 5분
    polling_interval = 5
    
    result_data = {}
    completed = False
    
    for i in range(max_retries):
        try:
            status_resp = client.get(
                f"/dementia/{analysis_id}",
                headers=headers
            )
            if status_resp.status_code != 200:
                print(f"\n❌ 분석 상태 조회 실패 (HTTP {status_resp.status_code})")
                sys.exit(1)
                
            result_data = status_resp.json()
            status = result_data.get("status")
            
            # 진행 표시
            sys.stdout.write(f"\r  ⏰ [{i+1:02d}s] 현재 분석 진행 상태: {status:<15}")
            sys.stdout.flush()
            
            if status == "completed":
                completed = True
                print("\n🎉 분석이 성공적으로 종료되었습니다!")
                break
            elif status == "failed":
                print("\n❌ 에러: OpenAI Whisper STT 또는 AI 분석 중 장애가 발생했습니다 (status: failed).")
                print("💡 .env 파일에 유효한 OPENAI_API_KEY 환경 변수가 등록되어 있는지 확인해 주세요.")
                sys.exit(1)
                
        except Exception as exc:
            print(f"\n❌ 폴링 중 에러 발생: {exc}")
            sys.exit(1)
            
        time.sleep(polling_interval)
        
    if not completed:
        print("\n❌ 타임아웃: 5분 이내에 분석이 완료되지 않았습니다.")
        sys.exit(1)

    # 5단계: 최종 리포트 출력
    print()
    print("=" * 60)
    print("📊 [최종] 치매 위험도 분석 E2E 통합 리포트")
    print("=" * 60)
    print(f"👤 분석 대상 ID   : {result_data.get('user_id')}")
    print(f"🆔 분석 고유 ID   : {result_data.get('analysis_id')}")
    print(f"🎙️ 변환 텍스트 (STT) :\n   \"{result_data.get('transcript', '')}\"")
    print("-" * 60)
    
    risk_level = result_data.get("risk_level", "low")
    risk_level_kr = {"low": "낮음 🟢", "medium": "보통 🟡", "high": "높음 🔴"}.get(risk_level, risk_level)
    
    print(f"🚨 치매 위험 등급  : {risk_level_kr}")
    print(f"📈 치매 위험 점수  : {result_data.get('risk_score', 0.0):.2f} (0.00 ~ 1.00)")
    print(f"💡 감지된 치매 지표 : {', '.join(result_data.get('indicators', [])) if result_data.get('indicators') else '없음'}")
    print("-" * 60)
    print(f"📝 AI 종합 분석 요약 :\n   {result_data.get('analysis_summary', '요약 없음')}")
    print("=" * 60)
    print("✅ E2E 통합 테스트가 성공적으로 종료되었습니다.")
    print("=" * 60)


if __name__ == "__main__":
    main()
