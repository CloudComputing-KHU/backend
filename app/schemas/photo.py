from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

PhotoStatus = Literal["sent", "scheduled"]
ReactionType = Literal["quick", "voice"]

class PhotoResponse(BaseModel):
    photo_id: str
    sender_user_id: str
    receiver_user_id: str
    image_url: str
    presigned_url: Optional[str] = None
    caption: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    status: PhotoStatus
    created_at: datetime

class QuickReactionRequest(BaseModel):
    label: str

class ReactionResponse(BaseModel):
    reaction_id: str
    photo_id: str
    user_id: str
    reaction_type: ReactionType
    label: Optional[str] = None
    voice_url: Optional[str] = None
    presigned_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    created_at: datetime
