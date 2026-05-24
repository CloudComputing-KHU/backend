# AGENTS.md

## Scope
- This file applies to the entire repository rooted at `backend/`.

## Project Identity
- This repository is the backend prototype for a cloud computing team project focused on reducing communication gaps between elderly parents and their adult children.
- The service is not a full chat app. It is a lightweight communication trigger built around:
  - daily health/meal/mood questions,
  - simple text or voice responses from the parent side,
  - photo sharing from the child side,
  - future AI-based anomaly detection and summary delivery.
- The intended UX direction from the presentation materials is:
  - parents: minimal, intuitive, low-friction interactions,
  - children: dashboard-style monitoring of health/activity signals and recent exchanges.

## Source Context
- Use these files as project-background references when making future decisions:
  - `resource/[E조] Presentations.pptx`
  - `resource/[437]spec_ppt_2026.pptx`
  - `README.md`
- The slide materials indicate planned expansion toward AWS-based deployment, AI integration, and child-facing monitoring features.

## Current Backend Reality
- Tech stack currently implemented:
  - `FastAPI` application in `app/main.py`
  - routers in `app/routers/`
  - schemas in `app/schemas/`
  - business logic in `app/services/`
- Current implementation is a mock/prototype, not production persistence:
  - question/answer data is stored in in-memory Python lists,
  - photo and voice files are uploaded to real S3 when `.env` is configured,
  - voice analysis is simulated with a background async task,
  - no real DB, scheduler, STT, Bedrock, or Rekognition integration is complete yet.

## Product Assumptions To Preserve
- Preserve the parent-child asymmetric workflow:
  - parent side answers simple prompts and receives photos,
  - child side uploads photos and reviews recent status/history.
- Favor low-complexity request flows and explicit API behavior over abstract architecture.
- Keep APIs easy for a frontend client to consume, especially for:
  - question retrieval,
  - answer submission,
  - voice upload status tracking,
  - photo upload/history retrieval.
- Treat AI features as progressive enhancement, not as a prerequisite for core flows.

## Development Priorities
- When changing this backend, prefer work that supports the roadmap implied by the materials:
  - in-memory mock logic -> DynamoDB or real persistence,
  - scheduled photo status -> real scheduler/event flow,
  - mock voice analysis -> actual STT/AI pipeline,
  - richer child monitoring summaries and alert-ready data.
- Maintain clear extension points instead of hard-coding production-specific behavior too early.
- Do not remove existing TODO markers unless the underlying integration is actually implemented.

## API Intent
- `GET /questions/{type}` serves daily prompts such as health, meal, and mood.
- `POST /answers/{type}` stores text-style responses.
- `POST /answers/{type}/voice` stores uploaded voice metadata and triggers async analysis flow.
- `POST /photos` uploads or schedules photos from sender to receiver.
- `GET /photos/history` returns photo transmission history for the sender side.

## Working Rules For Future Agents
- Before large design changes, align with this product framing: "elderly-friendly check-in and family connection service," not generic social media or chat.
- Keep the backend consistent with the current prototype style unless the user explicitly asks for a broader refactor.
- If adding persistence or AWS features, preserve the existing API contracts where reasonable.
- If requirements are ambiguous, choose the interpretation that best supports:
  - simple elderly UX,
  - child monitoring/awareness,
  - eventual cloud deployment and AI-assisted insight generation.

## Tooling Conventions
- Use `uv` as the default Python package and project manager for this repository.
- Treat `pyproject.toml` as the dependency and task source of truth.
- Prefer `uv sync --dev` to install dependencies for local development.
- Prefer `uv run <command>` for project-local execution instead of activating a virtual environment manually.
- Prefer `uv run poe <task>` for common workflows defined in `[tool.poe.tasks]`.
- Do not introduce or rely on root-level `requirements.txt` for the main backend unless the user explicitly asks for it.
- `httpx` is part of the development toolchain because FastAPI/Starlette `TestClient` depends on it for API verification.
- Record meaningful repository changes in `CHANGELOG.md` with date, author, and summary.

## AWS Integration Context
- Recommended rollout order:
  - S3 is already connected for voice and photo uploads,
  - keep metadata in mock/in-memory storage temporarily,
  - add DynamoDB after retrieval/statistics requirements stabilize.
- Expected environment variables for S3 integration:
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `DATA_AWS_REGION`
  - `S3_BUCKET_NAME`
  - `S3_VOICE_PREFIX`
  - `S3_PHOTO_PREFIX`
- Default assumption unless the user says otherwise:
  - `DATA_AWS_REGION=ap-northeast-2`
  - `AUTH_AWS_REGION=us-east-1`
- Future DynamoDB draft assumed in docs:
  - `answers` table for answer metadata and voice analysis state
  - `photos` table for photo transmission metadata

## Git Workflow
- This repository is configured for `git flow`.
- Current base branches are:
  - production branch: `main`
  - development branch: `dev`
- Preferred branch types are:
  - feature: `feat/<topic>`
  - bugfix: `bug/<topic>`
  - release: `rel/<version>`
  - hotfix: `hot/<topic>`
- Preferred commands when branch operations are explicitly requested:
  - `git flow feature start <topic>`
  - `git flow feature finish <topic>`
- Feature work should target `dev` first. Direct work on `main` should be limited to release/hotfix flow.
- If an agent is asked to create branches, commit, or push, it should follow this workflow unless the user gives different instructions.

## Commit Convention
- Do not create commits or push changes unless the user explicitly asks.
- When committing, use Conventional Commits style:
  - `feat(scope): add voice upload metadata handling`
  - `fix(answer): validate empty answer payload`
  - `docs(api): update answer statistics draft`
- Recommended commit types:
  - `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `ci`, `build`, `perf`
- Commit message rules:
  - format: `<type>(<scope>): <summary>`
  - use imperative mood
  - keep the summary concise
  - make scope match the touched area when useful, such as `answer`, `photo`, `api`, `aws`, `docs`
- If a body is needed, include:
  - why the change was needed
  - any API or schema impact
  - any follow-up work still pending

## Push Guidance
- For ongoing feature work, prefer pushing the feature branch first and merging into `dev` through the team workflow.
- Reserve pushes to `main` for approved release or hotfix steps.
- Before push, verify that changed docs and API behavior are aligned.

## Local Run Context
- Typical local run flow:
  - `uv sync --dev`
  - `uv run poe serve`
  - `uv run poe test`
