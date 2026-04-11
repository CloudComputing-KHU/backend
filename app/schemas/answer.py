from pydantic import BaseModel
from datetime import datetime
from typing import Literal, Optional
from app.schemas.question import QuestionType

AnswerType = Literal["choice", "voice"]
VoiceStatus = Literal["pending", "uploaded", "analyzed"]

class AnswerRequest(BaseModel):
    user_id: str
    question_id: str
    answer_type: AnswerType = "choice"
    answer: Optional[str] = None

class AnswerResponse(BaseModel):
    success: bool
    message: str

class AnswerItem(BaseModel):
    user_id: str
    question_id: str
    type: QuestionType
    answer_type: AnswerType
    answer: Optional[str]
    voice_status: Optional[VoiceStatus] = None
    voice_file_key: Optional[str] = None
    created_at: datetime
