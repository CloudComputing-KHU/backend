# 부모-자녀 안부 확인 서비스 — 백엔드

부모님의 일상(건강, 식사, 기분)을 확인하고 사진을 주고받는 앱의 백엔드 서버입니다.

## 기술 스택

- **Runtime**: Python 3.12 / FastAPI / uvicorn
- **Storage**: AWS S3 (음성, 사진 파일)
- **AI 분석**: AWS Transcribe (STT) → AWS Lambda + OpenAI GPT (치매 위험 감지)
- **인증**: AWS Cognito (이메일/비밀번호, JWT)
- **푸시 알림**: Firebase Admin SDK (FCM, Android/iOS 공통)
- **패키징**: uv + pyproject.toml

## 아키텍처 흐름

```
음성 업로드 → S3 저장 → AWS Transcribe (STT) → Lambda → OpenAI GPT → 치매 위험 분석 결과
```

## 현재 구현 상태

| 항목 | 상태 |
|------|------|
| 질문/답변/사진 API | 완료 |
| S3 파일 업로드 (음성, 사진) | 완료 |
| 사진 압축/리사이즈 | 완료 |
| 치매 위험 분석 API + Lambda | 완료 |
| DB 연동 (최종 DynamoDB 예정) | 진행 중 — 현재 Supabase로 메타데이터 영속화 |
| 수신 사진 조회 API | 완료 |
| 예약 사진 전송 스케줄러 | 완료 |
| Presigned URL (음성/사진 접근) | 완료 |
| STT 파이프라인 (Transcribe) | 코드 완성 — Lambda 배포 필요 |
| FCM 푸시 알림 | 완료 — Firebase 서비스 계정 설정 필요 |
| 회원가입 / 로그인 (Cognito) | 완료 |
| 부모-자녀 초대코드 연결 | 완료 |

---

## 프로젝트 구조

```text
app/
  ├── main.py                 
  ├── routers/                # API의 URL 경로와 요청/응답을 처리 역할
  │   ├── auth.py             # 회원가입, 이메일 인증, 로그인, 토큰 갱신 API
  │   ├── family.py           # 부모-자녀 초대코드 생성/연결 API
  │   ├── questions.py        # 질문 데이터 제공 관련 API
  │   ├── answers.py          # 답변 데이터 저장/조회 관련 API
  │   ├── photos.py           # 사진 전송 및 조회 관련 API
  │   ├── dementia.py         # 치매 위험 감지 분석 API
  │   └── devices.py          # FCM 디바이스 토큰 등록 API
  ├── schemas/                # 클라이언트와 주고받을 데이터 스키마 정의 (데이터 검증 역할)
  │   ├── auth.py             # 인증 요청/응답 데이터 형식
  │   ├── family.py           # 가족 연결 요청/응답 데이터 형식
  │   ├── question.py         # 질문 데이터 형식
  │   ├── answer.py           # 답변 데이터 형식
  │   ├── photo.py            # 사진 데이터 형식
  │   ├── dementia.py         # 치매 분석 요청/결과 데이터 형식
  │   └── device.py           # 디바이스 토큰 등록 형식
  └── services/               # 실제 비즈니스 로직(DB 저장, 필터링, 정렬 등)을 수행
      ├── auth_service.py     # Cognito 인증 및 JWT 검증 로직
      ├── family_service.py   # 부모-자녀 초대코드/연결 로직 (Supabase / 테스트 fallback)
      ├── question_service.py # 질문/답변 저장 로직 (Supabase / 테스트 fallback)
      ├── photo_service.py    # 사진/반응 저장 로직 (Supabase / 테스트 fallback)
      ├── dementia_service.py # 치매 분석 파이프라인 + 결과 저장 (Supabase / 테스트 fallback)
      ├── storage_service.py  # S3 파일 업로드 로직 (음성, 사진)
      ├── supabase_service.py # Supabase REST API 호출 로직
      ├── user_profile_service.py # Cognito 회원정보 → Supabase 프로필 동기화
      └── notification_service.py  # FCM 토큰/알림 저장 + 발송 로직
lambda/
  └── dementia_analyzer/
      ├── handler.py          # Lambda 함수 (OpenAI GPT 치매 분석)
      └── requirements.txt    # Lambda 의존성 (openai)
scripts/
  ├── check_voice_upload.py        # 음성 업로드 스모크 체크
  ├── check_dementia.py            # 치매 분석 요청 스모크 체크
  ├── test_lambda_integration.py   # Lambda 연동 테스트
  └── benchmark_photo.py           # 사진 압축 벤치마크
test/
  ├── test_answers_router.py  # 음성 업로드 API 테스트
  └── test_family_router.py   # 가족 연결 API 테스트
pyproject.toml                # uv / poe / dependency 설정
CHANGELOG.md                 # 날짜/작성자 기준 변경 이력
```

---

## 구현된 API 목록

### 인증

#### 1. 회원가입
- **POST** `/auth/signup`
- **요청 Body**: `role`(child/parent), `name`, `email`, `password`
- 가입 성공 시 이메일로 인증 코드 발송

#### 2. 이메일 인증
- **POST** `/auth/confirm`
- **요청 Body**: `email`, `confirmation_code`

#### 3. 로그인
- **POST** `/auth/login`
- **요청 Body**: `email`, `password`
- **응답**: `access_token`, `id_token`, `refresh_token`, `expires_in`
- 이후 API 호출 시 `Authorization: Bearer <id_token>` 헤더 사용

#### 4. 토큰 갱신
- **POST** `/auth/refresh`
- **요청 Body**: `refresh_token`
- **응답**: `access_token`, `id_token`, `expires_in`

#### 5. 가족 연결 초대 코드 생성 (자녀용)
- **POST** `/family/invites`
- **설명**: 자녀 계정이 부모님 연결용 4자리 숫자 초대 코드를 생성합니다.
- **인증/권한**: 로그인 필요, `child` 역할만 호출 가능
- **특징**:
  - 코드 길이는 4자리 숫자입니다.
  - 같은 자녀에게 아직 만료되지 않은 대기 코드가 있으면 그 코드를 재사용합니다.
  - 기본 만료 시간은 생성 후 10분입니다.
- **응답 예시**:
  ```json
  {
    "message": "가족 연결 초대 코드가 준비됐습니다.",
    "invite_code": "4821",
    "child_user_id": "child_001",
    "status": "pending",
    "created_at": "2026-05-23T20:10:00",
    "expires_at": "2026-05-23T20:20:00"
  }
  ```

#### 6. 가족 연결 코드 입력 (부모용)
- **POST** `/family/connect`
- **설명**: 부모 계정이 자녀가 생성한 4자리 숫자 초대 코드를 입력해 가족 연결을 완료합니다.
- **인증/권한**: 로그인 필요, `parent` 역할만 호출 가능
- **요청 Body**:
  ```json
  {
    "invite_code": "4821"
  }
  ```
- **응답 예시**:
  ```json
  {
    "message": "가족 연결이 완료됐습니다.",
    "link_id": "link_a1b2c3d4",
    "parent_user_id": "parent_001",
    "child_user_id": "child_001",
    "status": "active",
    "connected_at": "2026-05-23T20:11:00"
  }
  ```

#### 7. 내 가족 연결 상태 조회
- **GET** `/family/me`
- **설명**: 현재 로그인한 사용자의 가족 연결 상태를 조회합니다.
- **응답 특징**:
  - 연결 완료 전 자녀는 `pending_invite`로 현재 초대 코드를 확인할 수 있습니다.
  - 연결 완료 후 `active_link`에 부모/자녀 관계가 표시됩니다.
- **응답 예시**:
  ```json
  {
    "user_id": "child_001",
    "role": "child",
    "active_link": {
      "link_id": "link_a1b2c3d4",
      "parent_user_id": "parent_001",
      "child_user_id": "child_001",
      "status": "active",
      "connected_at": "2026-05-23T20:11:00"
    },
    "pending_invite": null
  }
  ```

#### Supabase 테이블 준비
- 현재 백엔드는 로컬 메모리 대신 Supabase에 메타데이터를 저장합니다.
- SQL Editor에서 `docs/supabase-family-schema.sql`을 먼저 실행해야 합니다.
- 파일명은 `family`로 시작하지만, 실제로는 아래 전체 테이블을 생성합니다.
  - `user_profiles`
  - `family_invites`
  - `family_links`
  - `answers`
  - `photos`
  - `photo_reactions`
  - `dementia_analyses`
  - `device_tokens`
  - `notifications`
- 실행 환경에서는 `ALLOW_IN_MEMORY_FALLBACK=false`를 유지하세요.
  - 이 값이 `false`면 Supabase 설정이 누락됐을 때 서버가 즉시 오류를 반환합니다.
  - 조용히 in-memory로 떨어져서 서버 재시작 때 가족 연결/답변/사진 이력이 사라지는 문제를 막기 위한 설정입니다.
- 필요한 환경변수는 `.env.example:27`에 정리돼 있습니다.

#### Supabase SQL Editor에서 실제로 할 일
1. Supabase 프로젝트에 들어갑니다.
2. 왼쪽 메뉴에서 `SQL Editor`를 엽니다.
3. `New query`를 누릅니다.
4. `backend/docs/supabase-family-schema.sql` 파일 내용을 전체 복사해서 붙여넣습니다.
5. `Run`을 눌러 실행합니다.
6. 실행 후 `Table Editor`에서 아래 테이블들이 생성됐는지 확인합니다.
   - `user_profiles`
   - `family_invites`
   - `family_links`
   - `answers`
   - `photos`
   - `photo_reactions`
   - `dementia_analyses`
   - `device_tokens`
   - `notifications`

이 작업을 해야 백엔드가 Supabase에 데이터를 저장할 수 있습니다. 이걸 하지 않으면 API는 테이블 없음 오류로 실패합니다.

---

> **인증 필요**: 아래 모든 API는 로그인 후 발급받은 `id_token`을 헤더에 포함해야 합니다.
> ```
> Authorization: Bearer <id_token>
> ```
> `user_id`는 토큰에서 자동 추출되므로 별도로 전달하지 않습니다.

---

### 1. 오늘의 질문 조회
- **GET** `/questions/{type}`
- **설명**: 부모님 화면에 띄울 질문과 선택지를 가져옵니다.
- **파라미터**: `type` (health, meal, mood 중 하나를 넘겨줍니다)

### 1-1. 오늘의 질문 진행 상태 조회
- **GET** `/questions/status/today`
- **설명**: 로그인한 부모 사용자의 오늘 질문 진행 상태를 영속 데이터 기준으로 조회합니다.
- **반환값**:
  - `health_answered`
  - `meal_answered`
  - `mood_answered`
  - `completed_count`
  - `next_type`
  - `all_answered`
- **용도**:
  - FE가 앱 재시작 후에도 로컬 step 상태가 아니라 서버 저장 상태로 질문 진행 단계를 복원할 때 사용합니다.

### 2. 질문에 대한 선택형(텍스트) 답변 저장
- **POST** `/answers/{type}`
- **설명**: 부모님이 선택하신 선택형 답변을 저장합니다. (저장 시 현재 시간 `created_at`이 자동 추가됩니다)
- **인증/권한**: 로그인 필요, `parent` 역할만 호출 가능
- **파라미터**: `type` 경로 파라미터
- **요청 Body**: `question_id`(질문 ID), `answer`(선택/입력한 텍스트)

### 3. 부모님 답변 목록 조회 (자녀용)
- **GET** `/answers/{type}`
- **설명**: 자녀가 부모님의 상태를 확인할 수 있도록, 연결된 부모가 남긴 답변들을 최신 시간순으로 정렬하여 보여줍니다.
- **파라미터**: `type` 경로 파라미터
- **특징**:
  - 부모가 호출하면 본인 답변을 조회합니다.
  - 자녀가 호출하면 연결된 부모의 답변을 조회합니다.
  - 가족 연결이 없으면 `409`를 반환합니다.
  - 음성 답변의 경우 `voice_status`와 함께 바로 재생 가능한 `voice_url` (Presigned URL, 7일 유효)도 함께 반환합니다.

### 4. 음성 답변 업로드
- **POST** `/answers/{type}/voice`
- **설명**: 부모님이 녹음하신 음성 파일(`.mp3`, `.wav`, `.m4a`)을 업로드합니다.
- **인증/권한**: 로그인 필요, `parent` 역할만 호출 가능
- **파라미터**: `type` 경로 파라미터
- **요청 Form**: `question_id`, `file` (Multipart/form-data)
- **특징**:
  - 파일 수신 시 확장자, MIME 타입, 빈 파일 여부, 최대 크기(10MB)를 검증합니다.
  - 업로드 성공 시 `answer_id`, 저장 파일명, 원본 파일명, 파일 크기, `voice_status`, `voice_url`을 함께 반환합니다.
  - `voice_url`은 7일간 유효한 Presigned URL로, 프론트엔드에서 바로 재생 가능합니다.
  - 파일 수신 즉시 `uploaded` 상태로 전환됩니다. STT 분석은 `/dementia/analyze` API를 통해 별도로 요청합니다.

### 5. 사진 전송 (즉시/예약)
- **POST** `/photos`
- **설명**: 서로의 일상 사진을 전송하거나 특정 시간에 전송되도록 예약합니다.
- **요청 Form**: `file`, `caption`(선택), `scheduled_at`(선택) (Multipart/form-data)
- **특징**:
  - 서버가 토큰의 현재 사용자와 가족 연결 정보를 기준으로 수신자를 자동 결정합니다.
  - 즉, 자녀는 연결된 부모에게, 부모는 연결된 자녀에게 전송됩니다.
  - 가족 연결이 없으면 `409`를 반환합니다.
  - `scheduled_at` 파라미터가 제공될 경우 `scheduled` 상태로 저장되며, 서버 내 asyncio 스케줄러가 해당 시간에 자동 발송 처리합니다.
  - 응답에 바로 열람 가능한 `presigned_url` (Presigned URL, 7일 유효)이 포함됩니다.

### 6. 사진 전송 내역 조회 (발신자 기준)
- **GET** `/photos/history`
- **설명**: 본인이 전송한 사진 목록을 최신순으로 조회합니다. 각 항목에 `presigned_url`이 포함됩니다.

### 7. 수신 사진 조회 — 새 사진만 (수신자 기준)
- **GET** `/photos/received`
- **설명**: 아직 확인하지 않은 사진(`status=sent`)만 반환합니다. 호출 시 해당 사진들의 상태가 자동으로 `seen`으로 변경됩니다. 각 항목에 `presigned_url`이 포함됩니다.

### 8. 수신 사진 전체 조회 (수신자 기준)
- **GET** `/photos/received/history`
- **설명**: 본인이 받은 사진 전체 목록을 최신순으로 조회합니다. `seen`, `sent` 상태 포함, 예약 중(`scheduled`) 제외. 각 항목에 `presigned_url`이 포함됩니다.

### 10. 치매 위험 분석 요청
- **POST** `/dementia/analyze`
- **설명**: 이미 업로드된 음성 답변에 대해 치매 위험 분석을 요청합니다.
- **요청 Body**: `answer_id`(음성 답변 ID)
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

### 11. 치매 분석 결과 조회
- **GET** `/dementia/{analysis_id}`
- **설명**: 특정 분석 건의 상세 결과를 조회합니다.
- **파라미터**: `analysis_id` 경로 파라미터
- **특징**:
  - 부모는 본인 분석 결과를 조회합니다.
  - 자녀는 연결된 부모의 분석 결과만 조회할 수 있습니다.
  - 권한이 없으면 `403`을 반환합니다.
  - 분석 진행 중이면 현재 `status`를, 완료 시 `risk_level`, `risk_score`, `analysis_summary`, `indicators`를 포함한 전체 결과를 반환합니다.
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

### 12. 사용자별 치매 분석 이력 조회
- **GET** `/dementia`
- **설명**:
  - 부모는 본인 치매 분석 이력을 조회합니다.
  - 자녀는 연결된 부모의 치매 분석 이력을 조회합니다.

### 13. FCM 디바이스 토큰 등록
- **POST** `/devices/register`
- **설명**: Flutter 앱에서 획득한 FCM 토큰을 백엔드에 등록합니다. 앱 실행 시마다 호출해 토큰을 최신 상태로 유지합니다.
- **요청 Body**: `fcm_token`
- **응답 예시**:
  ```json
  { "message": "Device registered" }
  ```

### 14. 알림 전체 조회
- **GET** `/notifications`
- **설명**: 내 알림 목록을 최신순으로 조회합니다. 읽은 알림 포함 전체 반환합니다.

### 15. 미읽음 알림 조회
- **GET** `/notifications/unread`
- **설명**: 읽지 않은 알림(`is_read=false`)만 최신순으로 반환합니다. 앱 뱃지 표시나 미확인 알림 목록에 사용합니다.

### 16. 알림 단건 읽음 처리
- **PATCH** `/notifications/{notification_id}/read`
- **설명**: 특정 알림을 읽음 처리합니다. 해당 알림이 없으면 `404`를 반환합니다.

### 17. 알림 전체 읽음 처리
- **PATCH** `/notifications/read-all`
- **설명**: 내 알림을 전부 읽음 처리합니다.

---

## 푸시 알림

Firebase Cloud Messaging(FCM)을 통해 Android/iOS 모두 지원합니다.

### 자동 발송 이벤트

| 이벤트 | 수신자 | 제목 |
|--------|--------|------|
| 사진 즉시 전송 | 사진 수신자 | 새 사진이 도착했어요 |
| 예약 사진 발송됨 | 사진 수신자 | 새 사진이 도착했어요 |
| 부모님 답변 제출 | `receiver_user_id` (자녀) | 새 답변이 도착했어요 |
| 치매 분석 완료 | 분석 요청한 본인 | 건강 분석이 완료됐어요 |

알림 `data` 페이로드에 `type`, `photo_id` / `analysis_id` 등이 포함되어 있어 Flutter에서 알림 탭 시 해당 화면으로 이동할 수 있습니다.


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
- Supabase 기반 메타데이터 영속화 추가
- Cognito 회원가입 시 Supabase `user_profiles` 동기화 추가
- 가족 연결/답변/사진/치매 분석/디바이스 토큰/알림 저장을 Supabase로 전환
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

- **Supabase 저장 사용**: 질문은 코드에 정적 보관하지만, 회원 프로필/가족 연결/답변/사진/사진 반응/치매 분석/디바이스 토큰/알림은 Supabase에 저장합니다.
- **S3 업로드 적용**: 음성 업로드와 사진 업로드 파일 본문은 현재 실제 AWS S3에 저장됩니다.
- **테스트 fallback 유지**: pytest에서는 외부 네트워크 없이 검증할 수 있도록 in-memory fallback backend를 유지합니다.
- **TODO 주석 활용**: 최종 목표는 DynamoDB 전환이며, 확장이 필요한 구간은 코드 내부 `# TODO:`로 유지합니다.

## 로컬 실행 방법

### 0) `.env` 파일 준비

```bash
cp .env.example .env
```

그 다음 `.env`에서 아래 값을 직접 채우면 됩니다.

```env
# AWS - Auth (Cognito)
AUTH_AWS_REGION=us-east-1
COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
COGNITO_APP_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx

# AWS - Data (S3 / Transcribe / future DynamoDB)
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
DATA_AWS_REGION=ap-northeast-2
S3_BUCKET_NAME=cloud-compute-team-e
S3_VOICE_PREFIX=voices
S3_PHOTO_PREFIX=photos
S3_URL_MODE=s3_uri

# Supabase
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key
SUPABASE_SCHEMA=public
SUPABASE_USER_PROFILES_TABLE=user_profiles
SUPABASE_FAMILY_INVITES_TABLE=family_invites
SUPABASE_FAMILY_LINKS_TABLE=family_links
SUPABASE_ANSWERS_TABLE=answers
SUPABASE_PHOTOS_TABLE=photos
SUPABASE_PHOTO_REACTIONS_TABLE=photo_reactions
SUPABASE_DEMENTIA_ANALYSES_TABLE=dementia_analyses
SUPABASE_DEVICE_TOKENS_TABLE=device_tokens
SUPABASE_NOTIFICATIONS_TABLE=notifications

# 푸시 알림 (둘 중 하나)
FIREBASE_SERVICE_ACCOUNT_PATH=/path/to/serviceAccountKey.json
# FIREBASE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
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

## 가족 연결 API 검증 방법

### 1. 자동 테스트 실행

```bash
UV_CACHE_DIR=.uv-cache uv run pytest test/test_family_router.py test/test_answers_router.py test/test_relation_based_routes.py -q
```

- `test/test_family_router.py`
  - 자녀 초대 코드 생성
  - 부모 코드 입력 연결
  - 역할 제한 검증
- `test/test_answers_router.py`
  - 음성 업로드 정상 처리
  - 잘못된 확장자 거부
- `test/test_relation_based_routes.py`
  - 자녀가 연결된 부모 답변 조회
  - 자녀가 연결된 부모 치매 분석 조회
  - 사진 전송 시 연결된 상대방으로 수신자 보정
  - 가족 연결 없을 때 `409` 반환

현재 구현 기준 위 명령은 통과했습니다.

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

아래 환경 변수를 `.env`에 설정하면 음성/사진 업로드가 실제 S3에 저장됩니다.

```env
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
DATA_AWS_REGION=ap-northeast-2
S3_BUCKET_NAME=...
S3_VOICE_PREFIX=voices
S3_PHOTO_PREFIX=photos
```

### 각 값 설명

- `AWS_ACCESS_KEY_ID`: 업로드 권한이 있는 IAM 사용자 또는 역할의 액세스 키
- `AWS_SECRET_ACCESS_KEY`: 해당 시크릿 키
- `DATA_AWS_REGION`: 버킷과 데이터 처리 리전
- `S3_BUCKET_NAME`: 실제 업로드 대상 버킷명
- `S3_VOICE_PREFIX`: 음성 파일을 저장할 S3 prefix
- `S3_PHOTO_PREFIX`: 사진 파일을 저장할 S3 prefix
- `AUTH_AWS_REGION`: Cognito User Pool 리전

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
