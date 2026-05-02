## 프로젝트 구조

```text
app/
  ├── main.py                 
  ├── routers/                # API의 URL 경로와 요청/응답을 처리 역할
  │   ├── questions.py        # 질문 데이터 제공 관련 API
  │   ├── answers.py          # 답변 데이터 저장/조회 관련 API
  │   ├── photos.py           # 사진 전송 및 조회 관련 API
  │   └── dementia.py         # 치매 위험 감지 분석 API
  ├── schemas/                # 클라이언트와 주고받을 데이터 스키마 정의 (데이터 검증 역할)
  │   ├── question.py         # 질문 데이터 형식
  │   ├── answer.py           # 답변 데이터 형식
  │   ├── photo.py            # 사진 데이터 형식
  │   └── dementia.py         # 치매 분석 요청/결과 데이터 형식
  └── services/               # 실제 비즈니스 로직(DB 저장, 필터링, 정렬 등)을 수행
      ├── question_service.py # 질문/답변 in-memory DB 로직
      ├── photo_service.py    # 사진 업로드 및 조회 in-memory DB 로직
      ├── ai_service.py       # (추후 확장용) 백그라운드 AI 분석 등 비동기 파이프라인 전담
      └── dementia_service.py # 치매 위험 감지 파이프라인 (S3→Transcribe→Lambda/OpenAI)
lambda/
  └── dementia_analyzer/
      ├── handler.py          # Lambda 함수 (OpenAI GPT 치매 분석)
      └── requirements.txt    # Lambda 의존성 (openai)
scripts/
  └── check_voice_upload.py   # 음성 업로드 스모크 체크 스크립트
test/
  └── test_answers_router.py  # 음성 업로드 API 테스트
pyproject.toml                # uv / poe / dependency 설정
CHANGELOG.md                 # 날짜/작성자 기준 변경 이력
```

---

## 구현된 API 목록

### 1. 오늘의 질문 조회
- **GET** `/questions/{type}`
- **설명**: 부모님 화면에 띄울 질문과 선택지를 가져옵니다.
- **파라미터**: `type` (health, meal, mood 중 하나를 넘겨줍니다)

### 2. 질문에 대한 선택형(텍스트) 답변 저장
- **POST** `/answers/{type}`
- **설명**: 부모님이 선택하신 선택형 답변을 저장합니다. (저장 시 현재 시간 `created_at`이 자동 추가됩니다)
- **파라미터**: `type` 경로 파라미터 
- **요청 Body**: `user_id`(유저 식별자), `question_id`(질문 ID), `answer`(선택/입력한 텍스트)

### 3. 부모님 답변 목록 조회 (자녀용)
- **GET** `/answers/{type}?user_id={user_id}`
- **설명**: 자녀가 부모님의 상태를 확인할 수 있도록, 특정 부모가 남긴 답변들을 최신 시간순으로 정렬하여 보여줍니다.
- **파라미터**: `type` 경로 파라미터 / `user_id` Query 파라미터
- **특징**: 일반 텍스트는 물론, 등록된 음성 답변의 상태(`voice_status`)도 함께 가져와 표시할 수 있게 설계되었습니다.

### 4. 음성 답변 업로드
- **POST** `/answers/{type}/voice`
- **설명**: 부모님이 녹음하신 음성 파일(`.mp3`, `.wav`, `.m4a`)을 업로드합니다.
- **파라미터**: `type` 경로 파라미터
- **요청 Form**: `user_id`, `question_id`, `file` (Multipart/form-data)
- **특징**:
  - 파일 수신 시 확장자, MIME 타입, 빈 파일 여부, 최대 크기(10MB)를 검증합니다.
  - 업로드 성공 시 `answer_id`, 저장 파일명, 원본 파일명, 파일 크기, `voice_status`를 함께 반환합니다.
  - 파일 수신 즉시 `uploaded` 상태로 전환되며, 백그라운드 파이프라인(STT) 처리가 완료되면 `analyzed` 상태로 업데이트됩니다.

### 5. 사진 전송 (즉시/예약)
- **POST** `/photos`
- **설명**: 서로의 일상 사진을 전송하거나 특정 시간에 전송되도록 예약합니다.
- **파라미터**: `file`, `sender_user_id`, `receiver_user_id`, `caption`, `scheduled_at` (Multipart/form-data)
- **특징**: `scheduled_at` 파라미터가 제공될 경우 `scheduled` 상태로 저장되어 추후 스케줄러에 의해 발송됩니다.

### 6. 사진 일상 전송 내역 조회
- **GET** `/photos/history?user_id={user_id}`
- **설명**: 특정 사용자(보낸 사람 기준)가 전송한 사진 목록과 그 상태를 최신 시간순으로 파악합니다.

### 7. 치매 위험 분석 요청
- **POST** `/dementia/analyze`
- **설명**: 이미 업로드된 음성 답변에 대해 치매 위험 분석을 요청합니다.
- **요청 Body**: `user_id`(부모 식별자), `answer_id`(음성 답변 ID)
- **동작 방식**:
  1. S3에 저장된 음성 파일을 AWS Transcribe로 전달하여 텍스트로 변환합니다.
  2. 변환된 텍스트를 Lambda + API Gateway (OpenAI GPT)에 전달하여 치매 위험 지표를 분석합니다.
  3. 분석은 백그라운드에서 비동기로 수행되며, 요청 즉시 `analysis_id`가 반환됩니다.
- **분석 기준**: 단어 찾기 어려움, 반복 발화, 문장 구조 단순화, 시간/장소 혼동, 주제 이탈, 기억 관련 표현, 발화 유창성
- **응답 예시**:
  ```json
  {
    "message": "치매 위험 분석이 요청되었습니다.",
    "analysis_id": "analysis_abc12345",
    "answer_id": "answer_9f8e7d6c",
    "user_id": "parent_001",
    "status": "pending",
    "created_at": "2026-04-30T14:00:00"
  }
  ```

### 8. 치매 분석 결과 조회
- **GET** `/dementia/{analysis_id}`
- **설명**: 특정 분석 건의 상세 결과를 조회합니다.
- **파라미터**: `analysis_id` 경로 파라미터
- **특징**: 분석 진행 중이면 현재 `status`를, 완료 시 `risk_level`, `risk_score`, `analysis_summary`, `indicators`를 포함한 전체 결과를 반환합니다.
- **응답 예시** (완료 시):
  ```json
  {
    "analysis_id": "analysis_abc12345",
    "answer_id": "answer_9f8e7d6c",
    "user_id": "parent_001",
    "status": "completed",
    "transcript": "오늘 약은... 그거... 먹었는데... 뭐였더라...",
    "risk_level": "medium",
    "risk_score": 0.6,
    "analysis_summary": "대명사 과다 사용과 단어 찾기 어려움이 관찰됩니다.",
    "indicators": ["단어 찾기 어려움", "기억 관련 표현"],
    "created_at": "2026-04-30T14:00:00",
    "completed_at": "2026-04-30T14:03:00"
  }
  ```

### 9. 사용자별 치매 분석 이력 조회
- **GET** `/dementia?user_id={user_id}`
- **설명**: 특정 부모의 치매 분석 이력을 최신순으로 조회합니다.
- **파라미터**: `user_id` Query 파라미터

---

## 개발 도구 기준

### `uv`를 기본으로 사용

- 이 프로젝트는 이제 `pip` 대신 `uv`를 기본 패키지/실행 도구로 사용합니다.
- 의존성의 기준 파일은 `requirements.txt`가 아니라 `pyproject.toml`입니다.
- 로컬 실행, 테스트, 스크립트 실행은 기본적으로 `uv run ...` 또는 `uv run poe ...` 형태로 진행합니다.

### `poe`를 단축 명령으로 사용

- 반복 실행 커맨드는 `pyproject.toml`의 `[tool.poe.tasks]`에 정의합니다.
- 현재 제공 작업:
  - `uv run poe serve`
  - `uv run poe test`
  - `uv run poe test-voice`
  - `uv run poe check-voice`
  - `uv run poe benchmark-photo`

## 주요 변경 사항

- `uv` 기반 의존성/실행 환경으로 전환
- `poe` 작업 명령 추가
- `.env.example` 추가
- 음성 업로드 S3 실연동
- 사진 업로드 S3 실연동
- AWS CLI와 `boto3` 기반 S3 적재 확인 절차 추가
- 중복 가상환경 `venv/` 제거, `.venv/`만 유지
- 변경 이력 문서 `CHANGELOG.md` 추가

자세한 변경 날짜/작성자/작업 내역은 `CHANGELOG.md`를 기준으로 관리합니다.

---

## 사진 업로드 최적화

### 개요

`POST /photos` 엔드포인트에서 S3 업로드 전 서버 측에서 사진을 자동 압축/리사이즈합니다.

### 동작 방식

1. **EXIF 회전 보정** — 세로로 찍힌 사진이 옆으로 눕히는 문제를 방지합니다
2. **리사이즈** — 가로/세로 중 긴 쪽이 1280px 초과 시 비율을 유지하며 자동 축소합니다
3. **포맷 변환**
   - 투명도 없음 → JPEG (quality=85)
   - 투명도 있음 (RGBA 등) → PNG (optimize=True) 유지

### 벤치마크 결과

> 측정 환경: Apple Silicon Mac, Python 3, Pillow, 5회 평균
> 합성 랜덤 픽셀 이미지 기준 — 실제 자연 사진은 압축률이 더 높게 측정됩니다

| 케이스 | 원본 | 압축 후 | 절감 | 처리 시간 |
|--------|------|--------|------|----------|
| 소형 JPEG (800×600) | 552KB | 312KB | **44%** | 16ms |
| 중형 JPEG (1920×1080, FHD) | 2.3MB | 500KB | **79%** | 77ms |
| 대형 JPEG (3024×4032, 12MP) | 13.6MB | 443KB | **97%** | 328ms |
| 대형 JPEG (4032×3024, 가로 12MP) | 13.6MB | 443KB | **97%** | 327ms |
| PNG 투명 (1000×1000, RGBA) | 3.9KB | 3.9KB | 0% | 9ms |
| **합계** | **30.1MB** | **1.7MB** | **94.5%** | — |

처리 시간은 서버 부하로 추가되지만, S3 업로드 시 네트워크 전송 절감 효과가 훨씬 큽니다.

### 벤치마크 직접 실행

```bash
uv run poe benchmark-photo

# 실제 사진 파일 지정 시
uv run python scripts/benchmark_photo.py photo1.jpg photo2.png
```

---

## 참고 및 확장 가이드

- **Mock 데이터 사용**: 답변/사진 메타데이터는 현재 DB 연결 없이 메모리 상주 리스트를 사용합니다. 서버 재시작 시 메타데이터는 초기화됩니다.
- **S3 업로드 적용**: 음성 업로드와 사진 업로드 파일 본문은 현재 실제 AWS S3에 저장됩니다.
- **TODO 주석 활용**: 향후 기능 확장이 필요한 구간(DynamoDB, AWS S3, 스케줄러 연동 등)은 모두 코드 내부에 `# TODO:` 주석으로 표기해 두었습니다.

## 로컬 실행 방법

### 0) `.env` 파일 준비

```bash
cp .env.example .env
```

그 다음 `.env`에서 아래 값을 직접 채우면 됩니다.

```env
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
AWS_REGION=ap-northeast-2
S3_BUCKET_NAME=cloud-compute-team-e
S3_VOICE_PREFIX=voices
S3_PHOTO_PREFIX=photos
S3_URL_MODE=s3_uri
```

`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`는 직접 편집해서 넣으면 됩니다.

### 1) 의존성 설치 및 동기화

```bash
uv sync --dev
```

### 2) FastAPI 서버 실행

```bash
uv run poe serve
```

실행 후 웹 브라우저에서 `http://127.0.0.1:8000/docs`에 접속하면 API 명세 확인 및 테스트를 바로 진행할 수 있습니다.

## 음성 업로드 검증 방법

### 1. 자동 스모크 체크

```bash
uv run poe check-voice
```

- `POST /answers/health/voice`를 로컬에서 호출합니다.
- 성공 시 업로드 응답과 `/answers/health` 조회 결과를 함께 출력합니다.

### 2. 테스트 실행

```bash
uv run poe test-voice
```

- 정상 음성 업로드
- 잘못된 확장자 거부

를 검증합니다.

### 3. Swagger UI로 수동 확인

```bash
uv run poe serve
```

서버 실행 후 `http://127.0.0.1:8000/docs`에서 아래처럼 테스트하면 됩니다.

- 엔드포인트: `POST /answers/{type}/voice`
- `type`: `health`
- `user_id`: `parent_001`
- `question_id`: `q_health_today`
- `file`: `.mp3`, `.wav`, `.m4a`

업로드 성공 시 응답의 `voice_file_key`에 `s3://cloud-compute-team-e/...` 형태가 반환됩니다.

## `httpx`가 필요한 이유

- FastAPI/Starlette의 `TestClient`는 내부적으로 `httpx`를 사용해 요청을 보냅니다.
- 그래서 테스트 코드나 스모크 체크 스크립트로 업로드 API를 검증하려면 `httpx`가 필요합니다.

## S3 적재 확인 명령어

### 1. FastAPI 업로드 테스트

```bash
uv run poe serve
```

그 다음 `http://127.0.0.1:8000/docs`에서

- `POST /answers/{type}/voice`
- `POST /photos`

를 실행하면 됩니다.

### 2. AWS CLI로 실제 적재 확인

응답에서 받은 `voice_file_key` 또는 `image_url`의 key 부분으로 아래처럼 확인할 수 있습니다.

```bash
set -a
source .env
set +a

aws s3api head-object \
  --bucket cloud-compute-team-e \
  --key voices/parent_001/<stored_filename>.m4a
```

사진은 아래처럼 확인합니다.

```bash
set -a
source .env
set +a

aws s3api head-object \
  --bucket cloud-compute-team-e \
  --key photos/child_001/<stored_filename>.jpeg
```

### 3. 이번 검증에서 실제 확인된 결과

- 음성 업로드 객체 적재 확인 완료
- 사진 업로드 객체 적재 확인 완료
- 검증 방식:
  - FastAPI 업로드 호출
  - `boto3 head_object`
  - `aws s3api head-object`

## AWS S3 연동 준비 정보

### 바로 주면 되는 값

아래 값들을 주면 내가 음성/사진 업로드를 실제 S3 저장 방식으로 연결할 수 있습니다.

```env
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-northeast-2
S3_BUCKET_NAME=...
S3_VOICE_PREFIX=voices
S3_PHOTO_PREFIX=photos
```

### 각 값 설명

- `AWS_ACCESS_KEY_ID`: 업로드 권한이 있는 IAM 사용자 또는 역할의 액세스 키
- `AWS_SECRET_ACCESS_KEY`: 해당 시크릿 키
- `AWS_REGION`: 버킷이 생성된 리전
- `S3_BUCKET_NAME`: 실제 업로드 대상 버킷명
- `S3_VOICE_PREFIX`: 음성 파일을 저장할 S3 prefix
- `S3_PHOTO_PREFIX`: 사진 파일을 저장할 S3 prefix

### 추가로 정하면 좋은 것

- 업로드 후 응답에 무엇을 저장할지
  - `s3://bucket/key`
  - 또는 `https://bucket.s3...`
- 버킷 public access 차단 유지 여부
- 추후 프론트에서 직접 조회할 때
  - 공개 URL 사용
  - 또는 presigned URL 사용

### AWS에서 먼저 만들어둘 것

- S3 버킷 1개
- 해당 버킷에 `PutObject`, `GetObject` 권한이 있는 IAM 사용자 또는 역할
- 필요 시 CORS 설정

### 추천 초기 구성

- 리전: `ap-northeast-2`
- 버킷 1개만 사용
- prefix 분리:
  - `voices/...`
  - `photos/...`
- public 공개는 일단 끄고 시작

## 추후 DynamoDB 연계 시 고려 중인 테이블 구조

현재는 S3 먼저 연동하고, DB는 나중에 붙이는 방향을 권장합니다. 다만 이후 DB 연계 시 아래 구조를 고려 중입니다.

### `answers` 테이블 초안

- 목적: 질문 답변, 음성 업로드 메타데이터, 분석 상태 저장
- 파티션 키 후보: `user_id`
- 정렬 키 후보: `created_at` 또는 `answer_id`

필드 후보:

- `answer_id`
- `user_id`
- `question_id`
- `type`
- `answer_type`
- `answer`
- `voice_status`
- `voice_file_key`
- `original_filename`
- `stored_filename`
- `content_type`
- `file_size`
- `created_at`
- `analyzed_at`

추가 인덱스 후보:

- `question_id` 기준 조회
- `voice_status` 기준 분석 대기 목록 조회

### `photos` 테이블 초안

- 목적: 사진 전송 메타데이터와 상태 저장
- 파티션 키 후보: `sender_user_id`
- 정렬 키 후보: `created_at` 또는 `photo_id`

필드 후보:

- `photo_id`
- `sender_user_id`
- `receiver_user_id`
- `image_url`
- `caption`
- `scheduled_at`
- `status`
- `created_at`

추가 인덱스 후보:

- `receiver_user_id` 기준 받은 사진 조회
- `status` 기준 예약 전송 목록 조회

### 사용자/관계 테이블은 나중 검토

- 현재는 `user_id` 문자열만 사용
- 부모-자녀 관계 관리가 필요해지면 별도 `users` 또는 관계 테이블 추가 검토
