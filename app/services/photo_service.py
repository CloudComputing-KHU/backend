import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional, List
from app.schemas.photo import PhotoStatus

logger = logging.getLogger(__name__)

# 사진 데이터를 저장할 in-memory mock 리스트
mock_photos = []

class PhotoService:
    @staticmethod
    def save_photo(
        sender_user_id: str,
        receiver_user_id: str,
        file_path: str,
        caption: Optional[str] = None,
        scheduled_at: Optional[datetime] = None
    ) -> dict:
        status: PhotoStatus = "scheduled" if scheduled_at else "sent"

        photo_record = {
            "photo_id": f"photo_{uuid.uuid4().hex[:8]}",
            "sender_user_id": sender_user_id,
            "receiver_user_id": receiver_user_id,
            "image_url": file_path,
            "caption": caption,
            "scheduled_at": scheduled_at,
            "status": status,
            "created_at": datetime.now()
        }
        mock_photos.append(photo_record)
        return photo_record

    @staticmethod
    def get_photo_history(user_id: str) -> List[dict]:
        filtered_photos = [p for p in mock_photos if p["sender_user_id"] == user_id]
        return sorted(filtered_photos, key=lambda x: x["created_at"], reverse=True)

    @staticmethod
    def get_received_photos(user_id: str) -> List[dict]:
        filtered_photos = [p for p in mock_photos if p["receiver_user_id"] == user_id and p["status"] == "sent"]
        return sorted(filtered_photos, key=lambda x: x["created_at"], reverse=True)

    @staticmethod
    async def schedule_dispatch(photo_record: dict) -> None:
        """scheduled_at까지 대기 후 status를 sent로 변경한다."""
        delay = (photo_record["scheduled_at"] - datetime.now()).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        photo_record["status"] = "sent"
        logger.info("예약 사진 발송 - photo_id=%s, receiver=%s", photo_record["photo_id"], photo_record["receiver_user_id"])

photo_service = PhotoService()
