# CHANGELOG

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
