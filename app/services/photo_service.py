import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException

from app.schemas.photo import PhotoStatus
from app.services.notification_service import notification_service
from app.services.supabase_service import supabase_service

mock_photos = []
mock_reactions = []


def normalize_scheduled_at(scheduled_at: Optional[datetime]) -> Optional[datetime]:
    if not scheduled_at:
        return None
    reference_tz = scheduled_at.tzinfo or timezone.utc
    now = datetime.now(reference_tz)
    if scheduled_at <= now:
        return None
    return scheduled_at


class InMemoryPhotoBackend:
    @staticmethod
    def save_photo(
        sender_user_id: str,
        receiver_user_id: str,
        file_path: str,
        caption: Optional[str] = None,
        scheduled_at: Optional[datetime] = None,
    ) -> dict:
        scheduled_at = normalize_scheduled_at(scheduled_at)
        status: PhotoStatus = "scheduled" if scheduled_at else "sent"
        photo_record = {
            "photo_id": f"photo_{uuid.uuid4().hex[:8]}",
            "sender_user_id": sender_user_id,
            "receiver_user_id": receiver_user_id,
            "image_url": file_path,
            "caption": caption,
            "scheduled_at": scheduled_at,
            "status": status,
            "created_at": datetime.now(),
        }
        mock_photos.append(photo_record)
        return photo_record

    @staticmethod
    def get_photo_history(user_id: str) -> List[dict]:
        filtered_photos = [p for p in mock_photos if p["sender_user_id"] == user_id]
        return sorted(filtered_photos, key=lambda x: x["created_at"], reverse=True)

    @staticmethod
    def get_received_photos(user_id: str) -> List[dict]:
        new_photos = [p for p in mock_photos if p["receiver_user_id"] == user_id and p["status"] == "sent"]
        for p in new_photos:
            p["status"] = "seen"
        return sorted(new_photos, key=lambda x: x["created_at"], reverse=True)

    @staticmethod
    def get_received_photos_history(user_id: str) -> List[dict]:
        filtered_photos = [p for p in mock_photos if p["receiver_user_id"] == user_id and p["status"] != "scheduled"]
        return sorted(filtered_photos, key=lambda x: x["created_at"], reverse=True)

    @staticmethod
    def get_photo(photo_id: str) -> dict | None:
        for photo in mock_photos:
            if photo["photo_id"] == photo_id:
                return photo
        return None

    @staticmethod
    def mark_photo_sent(photo_id: str) -> dict | None:
        photo = InMemoryPhotoBackend.get_photo(photo_id)
        if not photo:
            return None
        photo["status"] = "sent"
        return photo

    @staticmethod
    def get_scheduled_photos() -> List[dict]:
        return [p for p in mock_photos if p["status"] == "scheduled"]

    @staticmethod
    def get_reactions(photo_id: str) -> List[dict]:
        return [r for r in mock_reactions if r["photo_id"] == photo_id]

    @staticmethod
    def save_reaction(
        photo_id: str,
        user_id: str,
        reaction_type: str,
        label: Optional[str] = None,
        voice_url: Optional[str] = None,
        duration_seconds: Optional[int] = None,
    ) -> dict:
        record = {
            "reaction_id": f"reaction_{uuid.uuid4().hex[:8]}",
            "photo_id": photo_id,
            "user_id": user_id,
            "reaction_type": reaction_type,
            "label": label,
            "voice_url": voice_url,
            "duration_seconds": duration_seconds,
            "created_at": datetime.now(),
        }
        mock_reactions.append(record)
        return record


class SupabasePhotoBackend:
    @property
    def photos_table(self) -> str:
        return os.getenv("SUPABASE_PHOTOS_TABLE", "photos")

    @property
    def reactions_table(self) -> str:
        return os.getenv("SUPABASE_PHOTO_REACTIONS_TABLE", "photo_reactions")

    @staticmethod
    def is_configured() -> bool:
        return supabase_service.is_configured()

    def save_photo(
        self,
        sender_user_id: str,
        receiver_user_id: str,
        file_path: str,
        caption: Optional[str] = None,
        scheduled_at: Optional[datetime] = None,
    ) -> dict:
        scheduled_at = normalize_scheduled_at(scheduled_at)
        status: PhotoStatus = "scheduled" if scheduled_at else "sent"
        record = {
            "photo_id": f"photo_{uuid.uuid4().hex[:8]}",
            "sender_user_id": sender_user_id,
            "receiver_user_id": receiver_user_id,
            "image_url": file_path,
            "caption": caption,
            "scheduled_at": scheduled_at.isoformat() if isinstance(scheduled_at, datetime) else scheduled_at,
            "status": status,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return supabase_service.insert(self.photos_table, record)[0]

    def get_photo_history(self, user_id: str) -> List[dict]:
        return supabase_service.select(
            self.photos_table,
            filters=[("sender_user_id", f"eq.{user_id}")],
            order="created_at.desc",
        )

    def get_received_photos(self, user_id: str) -> List[dict]:
        new_photos = supabase_service.select(
            self.photos_table,
            filters=[("receiver_user_id", f"eq.{user_id}"), ("status", "eq.sent")],
            order="created_at.desc",
        )
        if new_photos:
            supabase_service.update(
                self.photos_table,
                filters=[("receiver_user_id", f"eq.{user_id}"), ("status", "eq.sent")],
                payload={"status": "seen"},
            )
            for p in new_photos:
                p["status"] = "seen"
        return new_photos

    def get_received_photos_history(self, user_id: str) -> List[dict]:
        return supabase_service.select(
            self.photos_table,
            filters=[("receiver_user_id", f"eq.{user_id}"), ("status", "neq.scheduled")],
            order="created_at.desc",
        )

    def get_scheduled_photos(self) -> List[dict]:
        return supabase_service.select(
            self.photos_table,
            filters=[("status", "eq.scheduled")],
            order="scheduled_at.asc",
        )

    def get_photo(self, photo_id: str) -> dict | None:
        rows = supabase_service.select(
            self.photos_table,
            filters=[("photo_id", f"eq.{photo_id}")],
            limit=1,
        )
        return rows[0] if rows else None

    def mark_photo_sent(self, photo_id: str) -> dict | None:
        rows = supabase_service.update(
            self.photos_table,
            filters=[("photo_id", f"eq.{photo_id}")],
            payload={"status": "sent"},
        )
        return rows[0] if rows else None

    def get_reactions(self, photo_id: str) -> List[dict]:
        return supabase_service.select(
            self.reactions_table,
            filters=[("photo_id", f"eq.{photo_id}")],
            order="created_at.desc",
        )

    def save_reaction(
        self,
        photo_id: str,
        user_id: str,
        reaction_type: str,
        label: Optional[str] = None,
        voice_url: Optional[str] = None,
        duration_seconds: Optional[int] = None,
    ) -> dict:
        record = {
            "reaction_id": f"reaction_{uuid.uuid4().hex[:8]}",
            "photo_id": photo_id,
            "user_id": user_id,
            "reaction_type": reaction_type,
            "label": label,
            "voice_url": voice_url,
            "duration_seconds": duration_seconds,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return supabase_service.insert(self.reactions_table, record)[0]


class PhotoService:
    def __init__(self) -> None:
        self._memory_backend = InMemoryPhotoBackend()
        self._supabase_backend = SupabasePhotoBackend()
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
            detail="Supabase is not configured for photo persistence.",
        )

    def save_photo(
        self,
        sender_user_id: str,
        receiver_user_id: str,
        file_path: str,
        caption: Optional[str] = None,
        scheduled_at: Optional[datetime] = None,
    ) -> dict:
        return self._backend().save_photo(
            sender_user_id=sender_user_id,
            receiver_user_id=receiver_user_id,
            file_path=file_path,
            caption=caption,
            scheduled_at=scheduled_at,
        )

    def get_photo_history(self, user_id: str) -> List[dict]:
        return self._backend().get_photo_history(user_id)

    def get_received_photos(self, user_id: str) -> List[dict]:
        return self._backend().get_received_photos(user_id)

    def get_received_photos_history(self, user_id: str) -> List[dict]:
        return self._backend().get_received_photos_history(user_id)

    def get_scheduled_photos(self) -> List[dict]:
        return self._backend().get_scheduled_photos()

    def mark_photo_sent(self, photo_id: str) -> dict | None:
        return self._backend().mark_photo_sent(photo_id)

    async def schedule_dispatch(self, photo_record: dict) -> None:
        scheduled_at = photo_record["scheduled_at"]
        if isinstance(scheduled_at, str):
            scheduled_at = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
        delay = (scheduled_at - datetime.now(scheduled_at.tzinfo or timezone.utc)).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        updated_photo = self._backend().mark_photo_sent(photo_record["photo_id"])
        if updated_photo:
            notification_service.send(
                user_id=updated_photo["receiver_user_id"],
                title="새 사진이 도착했어요",
                body=updated_photo.get("caption") or "가족이 사진을 보냈어요.",
                data={"photo_id": updated_photo["photo_id"], "type": "photo_received"},
            )

    def get_reactions(self, photo_id: str) -> List[dict]:
        return self._backend().get_reactions(photo_id)

    def get_photo(self, photo_id: str) -> dict | None:
        return self._backend().get_photo(photo_id)

    def save_reaction(
        self,
        photo_id: str,
        user_id: str,
        reaction_type: str,
        label: Optional[str] = None,
        voice_url: Optional[str] = None,
        duration_seconds: Optional[int] = None,
    ) -> dict:
        return self._backend().save_reaction(
            photo_id=photo_id,
            user_id=user_id,
            reaction_type=reaction_type,
            label=label,
            voice_url=voice_url,
            duration_seconds=duration_seconds,
        )


photo_service = PhotoService()
