# CHANGELOG

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
