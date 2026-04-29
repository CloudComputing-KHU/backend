# API Specification Draft

## 문서 목적
- 이 문서는 현재 프로젝트의 MVP 백엔드 API 초안이다.
- AWS, DB, AI 실연동 없이도 프론트와 백엔드가 맞춰볼 수 있는 수준의 명세를 우선 정의한다.
- 구현 확정 전 검토용 문서이므로, 필요한 기능 추가/삭제와 파라미터 조정이 가능하다.

## 제품 관점에서 필요한 사용자 흐름
- 부모
  - 오늘의 질문을 받는다.
  - 선택형 또는 음성으로 답변한다.
  - 자녀가 보낸 사진을 확인한다.
- 자녀
  - 부모의 최근 답변을 본다.
  - 사진을 보낸다.
  - 내가 보낸 사진 이력을 본다.

## 이번 단계의 권장 범위
- 포함
  - 질문 조회
  - 텍스트 답변 저장
  - 음성 답변 업로드
  - 답변 목록 조회
  - 사진 업로드
  - 보낸 사진 이력 조회
  - 받은 사진 목록 조회
- 보류
  - 로그인/인증
  - 푸시 알림
  - AI 요약 리포트
  - 이상징후 감지
  - 실제 예약 발송 스케줄러

## 공통 규칙
- Base URL: `/`
- 응답 시간 필드는 ISO 8601 문자열로 반환한다.
- 현재는 인증 없이 `user_id`로만 구분한다.
- 에러 응답 형식은 가급적 통일한다.

## 공통 에러 응답 예시
```json
{
  "detail": "Invalid extension"
}
```

## 1. 서버 상태 확인
### `GET /`
서버 정상 동작 확인용.

### Response `200`
```json
{
  "status": "ok",
  "message": "Server is running!"
}
```

## 2. 오늘의 질문 조회
### `GET /questions/{type}`
부모 앱에서 오늘 보여줄 질문 1개를 조회한다.

### Path Parameters
- `type`: `health | meal | mood`

### Response `200`
```json
{
  "question_id": "q_health_today",
  "type": "health",
  "text": "오늘 약은 드셨어요?",
  "options": [
    "네, 먹었어요",
    "아직 안 먹었어요",
    "약이 없어요",
    "기억이 안 나요"
  ],
  "allow_voice": true
}
```

### Response `404`
```json
{
  "detail": "해당 타입의 질문을 찾을 수 없습니다."
}
```

## 3. 선택형/텍스트 답변 저장
### `POST /answers/{type}`
부모가 질문에 대한 선택형 답변 또는 짧은 텍스트 답변을 저장한다.

### Path Parameters
- `type`: `health | meal | mood`

### Request Body
```json
{
  "user_id": "parent_001",
  "question_id": "q_health_today",
  "answer_type": "choice",
  "answer": "네, 먹었어요"
}
```

### Request Field Rules
- `user_id`: 부모 사용자 식별자
- `question_id`: 질문 식별자
- `answer_type`: 현재는 `choice`만 권장
- `answer`: 선택값 또는 직접 입력 텍스트

### Response `200`
```json
{
  "message": "Success"
}
```

## 4. 음성 답변 업로드
### `POST /answers/{type}/voice`
부모가 음성 답변 파일을 업로드한다. 현재 단계에서는 음성 메타데이터 저장과 분석 상태 시작까지만 처리한다.

### Path Parameters
- `type`: `health | meal | mood`

### Request
- Content-Type: `multipart/form-data`

### Form Data
- `user_id`: 부모 사용자 식별자
- `question_id`: 질문 식별자
- `file`: 음성 파일

### Allowed Extensions
- `.mp3`
- `.wav`
- `.m4a`

### Validation Rules
- 빈 파일은 허용하지 않는다.
- 최대 파일 크기는 `10MB`이다.
- MIME 타입은 오디오 업로드로 해석 가능한 값만 허용한다.

### Response `200`
```json
{
  "message": "Voice uploaded",
  "answer_id": "answer_9f8e7d6c",
  "voice_status": "uploaded",
  "voice_file_key": "s3://my-virtual-bucket/voices/parent_001/c8a1e2f3b4c5.m4a",
  "original_filename": "reply.m4a",
  "stored_filename": "c8a1e2f3b4c5.m4a",
  "content_type": "audio/x-m4a",
  "file_size": 245760,
  "created_at": "2026-04-29T14:20:00"
}
```

### Response `400`
```json
{
  "detail": "Invalid extension"
}
```

## 5. 부모 답변 목록 조회
### `GET /answers/{type}?user_id={user_id}`
자녀 앱에서 특정 부모의 질문 타입별 답변 이력을 최신순으로 조회한다.

### Path Parameters
- `type`: `health | meal | mood`

### Query Parameters
- `user_id`: 부모 사용자 식별자

### Response `200`
```json
[
  {
    "answer_id": "answer_1234abcd",
    "user_id": "parent_001",
    "question_id": "q_health_today",
    "type": "health",
    "answer_type": "choice",
    "answer": "네, 먹었어요",
    "voice_status": null,
    "voice_file_key": null,
    "original_filename": null,
    "stored_filename": null,
    "content_type": null,
    "file_size": null,
    "created_at": "2026-04-26T10:30:00"
  },
  {
    "answer_id": "answer_9f8e7d6c",
    "user_id": "parent_001",
    "question_id": "q_health_today",
    "type": "health",
    "answer_type": "voice",
    "answer": "[음성 인식 결과 예시]",
    "voice_status": "analyzed",
    "voice_file_key": "s3://my-virtual-bucket/voices/parent_001/c8a1e2f3b4c5.m4a",
    "original_filename": "reply.m4a",
    "stored_filename": "c8a1e2f3b4c5.m4a",
    "content_type": "audio/x-m4a",
    "file_size": 245760,
    "created_at": "2026-04-26T09:50:00"
  }
]
```

## 6. 사진 전송
### `POST /photos`
자녀가 부모에게 사진을 즉시 보내거나 예약 상태로 저장한다.

### Request
- Content-Type: `multipart/form-data`

### Form Data
- `sender_user_id`: 자녀 사용자 식별자
- `receiver_user_id`: 부모 사용자 식별자
- `caption`: 사진 설명, optional
- `scheduled_at`: 예약 전송 시각, optional
- `file`: 이미지 파일

### Allowed Extensions
- `.jpg`
- `.jpeg`
- `.png`

### Response `200`
```json
{
  "photo_id": "photo_a1b2c3d4",
  "sender_user_id": "child_001",
  "receiver_user_id": "parent_001",
  "image_url": "s3://my-virtual-bucket/photos/child_001/7f3a8b.jpeg",
  "caption": "오늘 점심 사진이에요",
  "scheduled_at": null,
  "status": "sent",
  "created_at": "2026-04-26T11:10:00"
}
```

### Response `400`
```json
{
  "detail": "Invalid extension"
}
```

## 7. 자녀가 보낸 사진 이력 조회
### `GET /photos/history?user_id={user_id}`
자녀가 자신이 보낸 사진 이력을 최신순으로 조회한다.

### Query Parameters
- `user_id`: 자녀 사용자 식별자

### Response `200`
```json
[
  {
    "photo_id": "photo_a1b2c3d4",
    "sender_user_id": "child_001",
    "receiver_user_id": "parent_001",
    "image_url": "s3://my-virtual-bucket/photos/child_001/7f3a8b.jpeg",
    "caption": "오늘 점심 사진이에요",
    "scheduled_at": null,
    "status": "sent",
    "created_at": "2026-04-26T11:10:00"
  }
]
```

## 8. 부모가 받은 사진 목록 조회
### `GET /photos/inbox?user_id={user_id}`
부모 앱에서 자신이 받은 사진 목록을 최신순으로 조회한다.

### 이유
- 현재 제품 흐름상 부모는 질문 응답뿐 아니라 자녀가 보낸 사진을 소비해야 한다.
- 이 API가 없으면 부모 화면의 핵심 피드 구성이 어렵다.
- 현재 코드에는 아직 없지만 MVP에는 필요한 API로 보는 것이 맞다.

### Query Parameters
- `user_id`: 부모 사용자 식별자

### Response `200`
```json
[
  {
    "photo_id": "photo_a1b2c3d4",
    "sender_user_id": "child_001",
    "receiver_user_id": "parent_001",
    "image_url": "s3://my-virtual-bucket/photos/child_001/7f3a8b.jpeg",
    "caption": "오늘 점심 사진이에요",
    "scheduled_at": null,
    "status": "sent",
    "created_at": "2026-04-26T11:10:00"
  }
]
```

## 이번 초안 기준에서 확인이 필요한 포인트
### 1. 질문 타입 구조
- 지금은 `health`, `meal`, `mood` 3종만 있다.
- 실제로는 하루에 여러 질문을 주는지, 질문 타입별 1개만 주는지 확정이 필요하다.

### 2. 답변 저장 방식
- `POST /answers/{type}`는 현재 `choice`와 자유 텍스트를 같이 받을 수 있게 보이지만, 실제 기획상 선택형만 허용할지 확인이 필요하다.

### 3. 사용자 식별 방식
- 지금은 모든 API가 `user_id` 문자열만 받는다.
- 추후 로그인 없이 갈지, 자녀/부모 관계를 따로 모델링할지 결정이 필요하다.

### 4. 사진 조회 관점
- 자녀 기준 `history`만으로 충분한지,
- 부모 기준 `inbox`가 반드시 필요한지,
- 사진 1건 상세 조회가 필요한지 정해야 한다.

### 5. 예약 전송 유지 여부
- `scheduled_at`를 지금 단계에서 유지할지,
- 아니면 MVP에서는 즉시 전송만 두고 예약은 제거할지 정리할 필요가 있다.

### 6. 응답 포맷 통일 여부
- 지금 구현은 일부는 객체, 일부는 배열, 일부는 `message`만 반환한다.
- 추후 `{ "data": ..., "message": ... }` 형식으로 통일할지 판단이 필요하다.

## 우선 추천하는 최소 구현 세트
- `GET /questions/{type}`
- `POST /answers/{type}`
- `POST /answers/{type}/voice`
- `GET /answers/{type}?user_id=...`
- `POST /photos`
- `GET /photos/history?user_id=...`
- `GET /photos/inbox?user_id=...`
