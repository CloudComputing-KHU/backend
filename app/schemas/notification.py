from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class NotificationItem(BaseModel):
    notification_id: str
    title: str
    body: str
    data: Optional[dict] = None
    is_read: bool
    created_at: datetime
