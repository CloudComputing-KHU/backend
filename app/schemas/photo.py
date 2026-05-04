from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

PhotoStatus = Literal["sent", "scheduled"]

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
