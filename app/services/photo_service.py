import uuid
from datetime import datetime
from typing import Optional, List
from app.schemas.photo import PhotoStatus

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
        # TODO: 실제 스케줄러 연동
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

photo_service = PhotoService()
