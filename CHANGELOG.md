# CHANGELOG

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
