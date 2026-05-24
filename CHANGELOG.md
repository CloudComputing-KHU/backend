# CHANGELOG

## 2026-05-25

### Author
- `jrne2` 
### Changes
- **OpenAI Whisper STT 파이프라인 전격 전환**:
  - AWS Learner Lab 환경의 IAM 권한 제약으로 사용 불가능했던 AWS Transcribe 의존성을 완전히 탈피하고, 고속 실시간 **OpenAI Whisper API (`whisper-1`)**를 직접 호출하여 STT를 수행하는 독자적 구조로 전면 리팩토링 (`app/services/dementia_service.py`).
  - S3에 업로드된 부모의 음성 파일을 서버 임시 오디오 파일로 로컬 다운로드한 뒤, OpenAI 클라이언트를 통해 초고속으로 한글 발화를 추출하는 안정적인 파이프라인 설계.
- **AWS Cognito 리전 세분화 및 JWT 시간 시차 오류 해결**:
  - Cognito 클라이언트 초기화 시 `.env`에 정의된 `AUTH_AWS_REGION` (us-east-1)을 정상 반영하도록 보수하여 400 Bad Request 인증 장애 해결 (`app/services/auth_service.py`).
  - 로컬 머신 시계와 Cognito 발급 토큰 간의 미세한 시간 차이로 발생하는 JWT 서명 검증 실패 (`ImmatureSignatureError: The token is not yet valid (iat)`) 현상을 `leeway=120` 매개변수 적용으로 원천 패치.
- **S3 리전 연동 유연화**:
  - S3 API 클라이언트 설정 시 `.env`의 `DATA_AWS_REGION` (ap-northeast-2) 환경변수를 최우선으로 수용하도록 조율하여 미디어 업로드 500 에러 극복 (`app/services/storage_service.py`).
- **테스트 환경 최적화 및 복구**:
  - `scripts/test_e2e_dementia.py`를 보완하여 UTF-8 쉘 환경에서의 Unicode 인코딩 충돌 없이 E2E 전체 흐름이 즉각 연동됨을 실증 검증 완료.
  - `scripts/check_dementia.py`를 Whisper 및 Cognito 프리패스 모킹 방식에 맞춰 개량 및 부활시켜, 인터넷/API 키가 전혀 없는 극한의 오프라인 로컬 환경에서도 0.1초 만에 전체 API 통신 규격을 완벽히 스모크 검증할 수 있는 무기로 개조.
  - `scripts/test_lambda_integration.py`의 모킹 구조를 Whisper 로직에 최적화하여 100% PASS 상태 달성.

### Verified
- Cognito 회원 인증 ➔ 실제 오디오 데이터 S3 저장 ➔ 실시간 S3 다운로드 및 OpenAI Whisper STT 한국어 변환 ➔ API Gateway를 통한 Lambda GPT 치매 분석 ➔ 등급판정 및 감지지표 최종 요약 리포트 수령까지 **E2E 전 과정 성공 확인**.
- API 키가 없는 상황에서의 로컬 오프라인 스모크 체크 시나리오 100% 정상 작동 완료.

---

## 2026-05-02

### Author
- `jrne2` 

### Changes
- Added dementia risk detection feature: full pipeline from voice analysis request to result retrieval.
- Created `app/schemas/dementia.py` — Pydantic schemas for analysis request/response/result/history.
- Created `app/routers/dementia.py` — 3 API endpoints: `POST /dementia/analyze`, `GET /dementia/{analysis_id}`, `GET /dementia?user_id=...`.
- Created `app/services/dementia_service.py` — Pipeline service: S3 URI parsing → Transcribe STT → Lambda(OpenAI) analysis, background async execution.
- Created `lambda/dementia_analyzer/handler.py` — AWS Lambda function that calls OpenAI GPT for dementia risk analysis with 7 clinical indicators.
- Created `lambda/dementia_analyzer/requirements.txt` — Lambda dependency (openai).
- Registered dementia router in `app/main.py` under `/dementia` prefix.
- Updated `.env.example`: removed `BEDROCK_MODEL_ID`, added `LLM_API_GATEWAY_URL` for API Gateway endpoint.
- Updated `README.md`: added lambda directory to project structure, updated dementia analysis description to reflect Lambda + API Gateway + OpenAI architecture.
- Created `scripts/test_lambda_integration.py` — Integration test script (S3/Transcribe mocked, Lambda/OpenAI real).
- Created `scripts/check_dementia.py` — Smoke test script for dementia API endpoints.
- Built Lambda deployment package with Linux-compatible binaries (`--platform manylinux2014_x86_64`).

### Architecture
- Initially implemented with Amazon Bedrock (Claude), then migrated to Lambda + API Gateway + OpenAI GPT due to Learner Lab restrictions on Bedrock access.
- OpenAI API key is stored only in Lambda environment variables — not exposed to the backend server.

### Verified
- API Gateway + Lambda + OpenAI GPT integration: dementia analysis returns `risk_level`, `risk_score`, `analysis_summary`, `indicators`.
- FastAPI pipeline (mock STT + real Lambda): `pending → transcribing → transcribed → analyzing → completed` status flow confirmed.
- Non-voice answer rejection returns 400 as expected.
- All integration tests passed (`scripts/test_lambda_integration.py`).

### Follow-up
- Connect S3 + Transcribe for real voice-to-text E2E pipeline.
- Add DynamoDB-backed persistence for analysis records (`mock_analyses` → DB).
- Optional: auto-trigger dementia analysis on voice upload (currently requires manual `/dementia/analyze` call).

---

## 2026-04-29

### Author
- `lazzyoung`

### Changes
- Added voice upload metadata flow with filename, content type, file size, and answer ID handling.
- Restored the main FastAPI app entry at `app/main.py`.
- Migrated the backend project to `uv` with `pyproject.toml` and `uv.lock`.
- Added `poe` task shortcuts for local serve, tests, voice checks, and photo benchmark.
- Added `.env.example` for AWS and S3 configuration.
- Connected voice uploads to real S3 storage.
- Connected photo uploads to real S3 storage.
- Verified S3 object existence with both `boto3` and `aws s3api head-object`.
- Removed duplicate local virtual environment directory `venv/` and kept `.venv/`.
- Documented AWS setup, DynamoDB draft schema, and local verification commands in `README.md`.

### Verified
- Voice upload API stores objects under `voices/<user_id>/...` in S3.
- Photo upload API stores objects under `photos/<user_id>/...` in S3.
- `uv sync --dev` succeeds with current project configuration.

### Follow-up
- Add DynamoDB-backed metadata persistence.
- Replace mock AI analysis with actual STT pipeline integration.
