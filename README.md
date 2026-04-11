## 프로젝트 구조

```text
app/
  ├── main.py                 
  ├── routers/                # API의 URL 경로와 요청/응답을 처리 역할
  │   ├── questions.py        # 질문 데이터 제공 관련 API
  │   ├── answers.py          # 답변 데이터 저장/조회 관련 API
  │   └── photos.py           # 사진 전송 및 조회 관련 API
  ├── schemas/                # 클라이언트와 주고받을 데이터 스키마 정의 (데이터 검증 역할)
  │   ├── question.py         # 질문 데이터 형식
  │   ├── answer.py           # 답변 데이터 형식
  │   └── photo.py            # 사진 데이터 형식
  └── services/               # 실제 비즈니스 로직(DB 저장, 필터링, 정렬 등)을 수행
      ├── question_service.py # 질문/답변 in-memory DB 로직
      ├── photo_service.py    # 사진 업로드 및 조회 in-memory DB 로직
      └── ai_service.py       # (추후 확장용) 백그라운드 AI 분석 등 비동기 파이프라인 전담
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
- **설명**: 부모님이 녹음하신 음성 파일(`.mp3`, `.wav`)을 업로드합니다.
- **파라미터**: `type` 경로 파라미터
- **요청 Form**: `user_id`, `question_id`, `file` (Multipart/form-data)
- **특징**: 파일 수신 즉시 `uploaded` 상태로 전환되며, 백그라운드 파이프라인(STT) 처리가 완료되면 `analyzed` 상태로 업데이트됩니다.

### 5. 사진 전송 (즉시/예약)
- **POST** `/photos`
- **설명**: 서로의 일상 사진을 전송하거나 특정 시간에 전송되도록 예약합니다.
- **파라미터**: `file`, `sender_user_id`, `receiver_user_id`, `caption`, `scheduled_at` (Multipart/form-data)
- **특징**: `scheduled_at` 파라미터가 제공될 경우 `scheduled` 상태로 저장되어 추후 스케줄러에 의해 발송됩니다.

### 6. 사진 일상 전송 내역 조회
- **GET** `/photos/history?user_id={user_id}`
- **설명**: 특정 사용자(보낸 사람 기준)가 전송한 사진 목록과 그 상태를 최신 시간순으로 파악합니다.

---

## 참고 및 확장 가이드

- **Mock 데이터 사용**: 현재는 DB 연결 없이 메모리 상주 리스트를 사용하고 있습니다. 서버 재시작 시 데이터가 초기화됩니다.
- **TODO 주석 활용**: 향후 기능 확장이 필요한 구간(DynamoDB, AWS S3, 스케줄러 연동 등)은 모두 코드 내부에 `# TODO:` 주석으로 표기해 두었습니다.

**로컬에서 실행하기:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

실행 후 웹 브라우저에서 `http://127.0.0.1:8000/docs`에 접속하면, API 명세 확인 및 테스트를 바로 진행할 수 있습니다
