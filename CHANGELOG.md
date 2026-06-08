# CHANGELOG

## 2026-06-08

### Author
- `kangtaeyeong`

### Changes
- Fixed `scripts/verify_imports.py` so it automatically adds the repository root to `sys.path` and can run without manual `PYTHONPATH=.`.
- Cleaned up `.env.example` formatting by removing invalid spaces around Cognito environment variables.
- Updated `.env.example` and `README.md` to reflect the current DynamoDB-based persistence setup instead of outdated Supabase guidance.
- Added validation records in `README.md` for:
  - DynamoDB table creation script
  - focused pytest suite
  - import verification script

### Verified
- `uv run python scripts/create_dynamodb_tables.py` 실행 시 DynamoDB 테이블 생성 또는 `[SKIP]` 확인.
- `uv run pytest test/test_questions_router.py test/test_answers_router.py test/test_family_router.py test/test_relation_based_routes.py -q` 통과.
- `uv run python scripts/verify_imports.py` 통과.

### Follow-up
- If `uv.lock` changed only as a local tooling side effect, keep it out of this docs/env cleanup PR unless dependency intent is explicit.

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

## 2026-05-25

### Author
- `kangtaeyeong`

### Changes
- Added `GET /questions/status/today` for persistent daily question progress lookup.
- Changed family/question/photo/dementia/notification services to stop silently falling back to in-memory storage unless `ALLOW_IN_MEMORY_FALLBACK=true` is explicitly enabled.
- Added family-link response name enrichment so `GET /family/me` returns `parent_name` and `child_name`.
- Normalized past/current `scheduled_at` values in photo upload so they are treated as immediate sends instead of delayed `scheduled` records.
- Removed obsolete client input parameters from request contracts:
  - `receiver_user_id` from `POST /answers/{type}`
  - `receiver_user_id` from `POST /photos`
- Updated backend request handling so answer notifications and photo receiver resolution rely only on token identity plus family-link data.
- Updated tests and README to match the simplified FE/BE contract.

### Verified
- `UV_CACHE_DIR=.uv-cache uv run pytest test/test_answers_router.py test/test_family_router.py test/test_relation_based_routes.py -q` 통과.

### Follow-up
- Remove now-obsolete FE request arguments that manually pass receiver or family user identifiers.
- Decide whether past `scheduled_at` should be auto-sent or rejected with validation in the final product policy.

## 2026-05-24

### Author
- `kangtaeyeong`

### Changes
- Expanded temporary persistence from family-link only to broad Supabase metadata persistence.
- Added Supabase-backed storage for:
  - `user_profiles`
  - `family_invites`
  - `family_links`
  - `answers`
  - `photos`
  - `photo_reactions`
  - `dementia_analyses`
  - `device_tokens`
  - `notifications`
- Added `app/services/user_profile_service.py` to sync Cognito sign-up / token claims into Supabase profiles.
- Updated `auth_service` so sign-up confirmation and protected-route access keep Supabase user profiles synchronized.
- Reworked question/photo/dementia/notification services to use Supabase with in-memory fallback for tests.
- Expanded `docs/supabase-family-schema.sql` into a full app metadata schema setup file.
- Updated `.env.example`, `README.md`, and `AGENTS.md` with the new Supabase scope and setup instructions.

### Verified
- `UV_CACHE_DIR=.uv-cache uv run pytest test/test_family_router.py test/test_answers_router.py test/test_relation_based_routes.py -q` 통과.

### Follow-up
- Execute `docs/supabase-family-schema.sql` in Supabase SQL Editor before runtime verification.
- Connect FE family screens to the live family APIs.
- Replace Supabase temporary persistence with DynamoDB if the final architecture is fixed on AWS-only infrastructure.

---

## 2026-05-24

### Author
- `kangtaeyeong`

### Changes
- Added Supabase REST integration support for family invite and family link persistence.
- Added `app/services/supabase_service.py` for backend-only Supabase API access using the service role key.
- Reworked `app/services/family_service.py` to support Supabase-backed family persistence with in-memory fallback for tests.
- Added `docs/supabase-family-schema.sql` for `family_invites` and `family_links` table creation.
- Updated `GET /answers/{type}` so child users read answers from their linked parent.
- Updated `GET /dementia` and `GET /dementia/{analysis_id}` so child users read analyses from their linked parent.
- Updated `POST /photos` so parent/child users always send to their linked family member instead of trusting the client-provided receiver id.
- Added `test/test_relation_based_routes.py` to verify linked-parent answer lookup, dementia lookup, and relation-based photo delivery.
- Updated `README.md` and `.env.example` with Supabase setup guidance.

### Verified
- `UV_CACHE_DIR=.uv-cache uv run pytest test/test_family_router.py test/test_answers_router.py test/test_relation_based_routes.py -q` 통과.

### Follow-up
- Connect FE family screens to `/family/invites`, `/family/connect`, and `/family/me`.
- Replace in-memory answer/photo/dementia metadata with real persistence after family-link flow stabilizes.

---

## 2026-05-24

### Author
- `kangtaeyeong`

### Changes
- Split AWS region configuration by responsibility.
- Updated Cognito-related code to use `AUTH_AWS_REGION`.
- Updated S3/Transcribe-related code to use `DATA_AWS_REGION`.
- Updated `.env.example`, `README.md`, and `AGENTS.md` to document the separated region variables.

### Verified
- `UV_CACHE_DIR=.uv-cache uv run pytest test/test_family_router.py test/test_answers_router.py -q` 통과.

### Follow-up
- Apply the same region separation when DynamoDB is added.

---

## 2026-05-23

### Author
- `kangtaeyeong`

### Changes
- Added parent-child family linking APIs based on 4-digit invite codes.
- Created `app/routers/family.py` with `POST /family/invites`, `POST /family/connect`, and `GET /family/me`.
- Created `app/schemas/family.py` for invite/link request and response models.
- Created `app/services/family_service.py` for in-memory invite issuance, expiration, and active link management.
- Registered the family router in `app/main.py`.
- Added `test/test_family_router.py` to verify invite creation, parent connection, and role restrictions.
- Updated `README.md` to document the new family-linking flow and API examples.

### Verified
- Child users can create 4-digit invite codes.
- Parent users can connect with a valid invite code.
- Role restriction checks return 403 for invalid caller roles.
- `UV_CACHE_DIR=.uv-cache uv run pytest test/test_family_router.py test/test_answers_router.py -q` 통과.

### Follow-up
- Persist family invites and links in DynamoDB instead of in-memory storage.
- Replace hardcoded family-user assumptions in FE data providers with `/family/me` results.

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
