from pydantic import BaseModel
from datetime import datetime
from typing import Literal, Optional
from app.schemas.question import QuestionType

AnswerType = Literal["choice", "voice"]
VoiceStatus = Literal["pending", "uploaded", "analyzed"]


class AnswerRequest(BaseModel):
    question_id: str
    answer_type: AnswerType = "choice"
    answer: Optional[str] = None


class AnswerResponse(BaseModel):
    message: str


class VoiceUploadResponse(BaseModel):
    message: str
    answer_id: str
    voice_status: VoiceStatus
    voice_file_key: str
    voice_url: Optional[str] = None
    original_filename: str
    stored_filename: str
    content_type: Optional[str] = None
    file_size: int
    created_at: datetime


class AnswerItem(BaseModel):
    answer_id: str
    user_id: str
    question_id: str
    type: QuestionType
    answer_type: AnswerType
    answer: Optional[str]
    voice_status: Optional[VoiceStatus] = None
    voice_file_key: Optional[str] = None
    voice_url: Optional[str] = None
    original_filename: Optional[str] = None
    stored_filename: Optional[str] = None
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    created_at: datetime
