import os
import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException

from app.schemas.answer import AnswerRequest
from app.schemas.question import Question, QuestionType
from app.services.supabase_service import supabase_service

mock_questions = {
    "health": [
        Question(
            question_id="q_health_today",
            type="health",
            text="오늘 약은 드셨어요?",
            options=["네, 먹었어요", "아직 안 먹었어요", "약이 없어요", "기억이 안 나요"],
            allow_voice=True,
        )
    ],
    "meal": [
        Question(
            question_id="q_meal_today",
            type="meal",
            text="오늘 식사는 잘 하셨어요?",
            options=["네, 잘 먹었어요", "아직 안 먹었어요", "간단히 먹었어요", "기억이 안 나요"],
            allow_voice=True,
        )
    ],
    "mood": [
        Question(
            question_id="q_mood_today",
            type="mood",
            text="오늘 기분이 어떠세요?",
            options=["좋아요", "괜찮아요", "좀 피곤해요", "안 좋아요"],
            allow_voice=True,
        )
    ],
}

mock_answers = []


class InMemoryQuestionBackend:
    @staticmethod
    def save_answer(q_type: QuestionType, request: AnswerRequest, user_id: str) -> dict:
        answer_record = {
            "answer_id": f"answer_{uuid.uuid4().hex[:8]}",
            "type": q_type,
            "user_id": user_id,
            "question_id": request.question_id,
            "answer_type": request.answer_type,
            "answer": request.answer,
            "voice_status": None,
            "voice_file_key": None,
            "original_filename": None,
            "stored_filename": None,
            "content_type": None,
            "file_size": None,
            "created_at": datetime.now(),
        }
        mock_answers.append(answer_record)
        return answer_record

    @staticmethod
    def save_voice_answer_metadata(
        q_type: QuestionType,
        user_id: str,
        question_id: str,
        file_path: str,
        original_filename: str,
        stored_filename: str,
        content_type: str | None,
        file_size: int,
    ) -> dict:
        answer_record = {
            "answer_id": f"answer_{uuid.uuid4().hex[:8]}",
            "type": q_type,
            "user_id": user_id,
            "question_id": question_id,
            "answer_type": "voice",
            "answer": None,
            "voice_status": "uploaded",
            "voice_file_key": file_path,
            "original_filename": original_filename,
            "stored_filename": stored_filename,
            "content_type": content_type,
            "file_size": file_size,
            "created_at": datetime.now(),
        }
        mock_answers.append(answer_record)
        return answer_record

    @staticmethod
    def get_user_answers(q_type: QuestionType, user_id: str) -> list[dict]:
        filtered_answers = [
            ans for ans in mock_answers if ans["type"] == q_type and ans["user_id"] == user_id
        ]
        return sorted(filtered_answers, key=lambda x: x["created_at"], reverse=True)

    @staticmethod
    def has_answered_today(q_type: QuestionType, user_id: str) -> bool:
        today = date.today()
        for ans in mock_answers:
            if ans["type"] == q_type and ans["user_id"] == user_id:
                created_at = ans["created_at"]
                if isinstance(created_at, datetime) and created_at.date() == today:
                    return True
        return False

    @staticmethod
    def get_answer_by_id(answer_id: str) -> dict | None:
        for answer in mock_answers:
            if answer["answer_id"] == answer_id:
                return answer
        return None


class SupabaseQuestionBackend:
    @property
    def table(self) -> str:
        return os.getenv("SUPABASE_ANSWERS_TABLE", "answers")

    @staticmethod
    def is_configured() -> bool:
        return supabase_service.is_configured()

    def save_answer(self, q_type: QuestionType, request: AnswerRequest, user_id: str) -> dict:
        record = {
            "answer_id": f"answer_{uuid.uuid4().hex[:8]}",
            "type": q_type,
            "user_id": user_id,
            "question_id": request.question_id,
            "answer_type": request.answer_type,
            "answer": request.answer,
            "voice_status": None,
            "voice_file_key": None,
            "original_filename": None,
            "stored_filename": None,
            "content_type": None,
            "file_size": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return supabase_service.insert(self.table, record)[0]

    def save_voice_answer_metadata(
        self,
        q_type: QuestionType,
        user_id: str,
        question_id: str,
        file_path: str,
        original_filename: str,
        stored_filename: str,
        content_type: str | None,
        file_size: int,
    ) -> dict:
        record = {
            "answer_id": f"answer_{uuid.uuid4().hex[:8]}",
            "type": q_type,
            "user_id": user_id,
            "question_id": question_id,
            "answer_type": "voice",
            "answer": None,
            "voice_status": "uploaded",
            "voice_file_key": file_path,
            "original_filename": original_filename,
            "stored_filename": stored_filename,
            "content_type": content_type,
            "file_size": file_size,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return supabase_service.insert(self.table, record)[0]

    def get_user_answers(self, q_type: QuestionType, user_id: str) -> list[dict]:
        return supabase_service.select(
            self.table,
            filters=[("type", f"eq.{q_type}"), ("user_id", f"eq.{user_id}")],
            order="created_at.desc",
        )

    def has_answered_today(self, q_type: QuestionType, user_id: str) -> bool:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        results = supabase_service.select(
            self.table,
            filters=[
                ("type", f"eq.{q_type}"),
                ("user_id", f"eq.{user_id}"),
                ("created_at", f"gte.{today_start}"),
            ],
            limit=1,
        )
        return len(results) > 0

    def get_answer_by_id(self, answer_id: str) -> dict | None:
        results = supabase_service.select(
            self.table,
            filters=[("answer_id", f"eq.{answer_id}")],
            limit=1,
        )
        return results[0] if results else None


class QuestionService:
    def __init__(self) -> None:
        self._memory_backend = InMemoryQuestionBackend()
        self._supabase_backend = SupabaseQuestionBackend()
        self._backend_override = None

    def set_backend(self, backend) -> None:
        self._backend_override = backend

    def reset_backend(self) -> None:
        self._backend_override = None

    def _backend(self):
        if self._backend_override is not None:
            return self._backend_override
        if self._supabase_backend.is_configured():
            return self._supabase_backend
        if os.getenv("ALLOW_IN_MEMORY_FALLBACK", "").lower() == "true":
            return self._memory_backend
        raise HTTPException(
            status_code=500,
            detail="Supabase is not configured for question persistence.",
        )

    @staticmethod
    def get_todays_question(q_type: QuestionType) -> Question | None:
        questions = mock_questions.get(q_type, [])
        return questions[0] if questions else None

    def save_answer(self, q_type: QuestionType, request: AnswerRequest, user_id: str) -> dict:
        return self._backend().save_answer(q_type, request, user_id)

    def save_voice_answer_metadata(
        self,
        q_type: QuestionType,
        user_id: str,
        question_id: str,
        file_path: str,
        original_filename: str,
        stored_filename: str,
        content_type: str | None,
        file_size: int,
    ) -> dict:
        return self._backend().save_voice_answer_metadata(
            q_type,
            user_id,
            question_id,
            file_path,
            original_filename,
            stored_filename,
            content_type,
            file_size,
        )

    def get_user_answers(self, q_type: QuestionType, user_id: str) -> list[dict]:
        return self._backend().get_user_answers(q_type, user_id)

    def has_answered_today(self, q_type: QuestionType, user_id: str) -> bool:
        return self._backend().has_answered_today(q_type, user_id)

    def get_answer_by_id(self, answer_id: str) -> dict | None:
        return self._backend().get_answer_by_id(answer_id)

    def get_daily_progress(self, user_id: str) -> dict:
        progress = {
            "health_answered": self.has_answered_today("health", user_id),
            "meal_answered": self.has_answered_today("meal", user_id),
            "mood_answered": self.has_answered_today("mood", user_id),
        }
        completed_count = sum(1 for answered in progress.values() if answered)
        next_type = None
        for q_type in ("health", "meal", "mood"):
            if not progress[f"{q_type}_answered"]:
                next_type = q_type
                break
        return {
            "user_id": user_id,
            **progress,
            "completed_count": completed_count,
            "next_type": next_type,
            "all_answered": completed_count == 3,
        }


question_service = QuestionService()
