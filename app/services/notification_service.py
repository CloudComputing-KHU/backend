import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.services.supabase_service import supabase_service

logger = logging.getLogger(__name__)

_device_tokens: dict[str, str] = {}
_notifications: dict[str, list[dict]] = {}


class InMemoryNotificationBackend:
    @staticmethod
    def register_token(user_id: str, fcm_token: str) -> None:
        _device_tokens[user_id] = fcm_token

    @staticmethod
    def get_token(user_id: str) -> Optional[str]:
        return _device_tokens.get(user_id)

    @staticmethod
    def save_notification(user_id: str, title: str, body: str, data: Optional[dict]) -> dict:
        record = {
            "notification_id": uuid.uuid4().hex,
            "user_id": user_id,
            "title": title,
            "body": body,
            "data": data,
            "is_read": False,
            "created_at": datetime.now(timezone.utc),
        }
        _notifications.setdefault(user_id, []).insert(0, record)
        return record

    @staticmethod
    def get_notifications(user_id: str) -> list[dict]:
        return _notifications.get(user_id, [])

    @staticmethod
    def get_unread_notifications(user_id: str) -> list[dict]:
        return [n for n in _notifications.get(user_id, []) if not n["is_read"]]

    @staticmethod
    def mark_read(notification_id: str, user_id: str) -> bool:
        for n in _notifications.get(user_id, []):
            if n["notification_id"] == notification_id:
                n["is_read"] = True
                return True
        return False

    @staticmethod
    def mark_all_read(user_id: str) -> None:
        for n in _notifications.get(user_id, []):
            n["is_read"] = True


class SupabaseNotificationBackend:
    @property
    def device_tokens_table(self) -> str:
        return os.getenv("SUPABASE_DEVICE_TOKENS_TABLE", "device_tokens")

    @property
    def notifications_table(self) -> str:
        return os.getenv("SUPABASE_NOTIFICATIONS_TABLE", "notifications")

    @staticmethod
    def is_configured() -> bool:
        return supabase_service.is_configured()

    def register_token(self, user_id: str, fcm_token: str) -> None:
        supabase_service.upsert(
            self.device_tokens_table,
            {
                "user_id": user_id,
                "fcm_token": fcm_token,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="user_id",
        )

    def get_token(self, user_id: str) -> Optional[str]:
        rows = supabase_service.select(
            self.device_tokens_table,
            filters=[("user_id", f"eq.{user_id}")],
            limit=1,
        )
        if not rows:
            return None
        return rows[0].get("fcm_token")

    def save_notification(self, user_id: str, title: str, body: str, data: Optional[dict]) -> dict:
        record = {
            "notification_id": uuid.uuid4().hex,
            "user_id": user_id,
            "title": title,
            "body": body,
            "data": data,
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return supabase_service.insert(self.notifications_table, record)[0]

    def get_notifications(self, user_id: str) -> list[dict]:
        return supabase_service.select(
            self.notifications_table,
            filters=[("user_id", f"eq.{user_id}")],
            order="created_at.desc",
        )

    def get_unread_notifications(self, user_id: str) -> list[dict]:
        return supabase_service.select(
            self.notifications_table,
            filters=[("user_id", f"eq.{user_id}"), ("is_read", "eq.false")],
            order="created_at.desc",
        )

    def mark_read(self, notification_id: str, user_id: str) -> bool:
        rows = supabase_service.update(
            self.notifications_table,
            filters=[("notification_id", f"eq.{notification_id}"), ("user_id", f"eq.{user_id}")],
            payload={"is_read": True},
        )
        return len(rows) > 0

    def mark_all_read(self, user_id: str) -> None:
        supabase_service.update(
            self.notifications_table,
            filters=[("user_id", f"eq.{user_id}"), ("is_read", "eq.false")],
            payload={"is_read": True},
        )


class NotificationService:
    def __init__(self) -> None:
        self._app = None
        self._memory_backend = InMemoryNotificationBackend()
        self._supabase_backend = SupabaseNotificationBackend()
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
        return self._memory_backend

    def _get_app(self):
        import firebase_admin
        from firebase_admin import credentials

        if firebase_admin._apps:
            return firebase_admin.get_app()

        service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")

        if service_account_json:
            cred = credentials.Certificate(json.loads(service_account_json))
        elif service_account_path:
            cred = credentials.Certificate(service_account_path)
        else:
            raise RuntimeError(
                "Firebase credentials not configured. "
                "Set FIREBASE_SERVICE_ACCOUNT_JSON or FIREBASE_SERVICE_ACCOUNT_PATH."
            )

        self._app = firebase_admin.initialize_app(cred)
        return self._app

    def register_token(self, user_id: str, fcm_token: str) -> None:
        self._backend().register_token(user_id, fcm_token)
        logger.info("FCM 토큰 등록 - user_id=%s", user_id)

    def get_token(self, user_id: str) -> Optional[str]:
        return self._backend().get_token(user_id)

    def _save_notification(self, user_id: str, title: str, body: str, data: Optional[dict]) -> dict:
        return self._backend().save_notification(user_id, title, body, data)

    def get_notifications(self, user_id: str) -> list[dict]:
        return self._backend().get_notifications(user_id)

    def get_unread_notifications(self, user_id: str) -> list[dict]:
        return self._backend().get_unread_notifications(user_id)

    def mark_read(self, notification_id: str, user_id: str) -> bool:
        return self._backend().mark_read(notification_id, user_id)

    def mark_all_read(self, user_id: str) -> None:
        self._backend().mark_all_read(user_id)

    def send(self, user_id: str, title: str, body: str, data: Optional[dict] = None) -> bool:
        self._save_notification(user_id, title, body, data)
        token = self.get_token(user_id)
        if not token:
            logger.warning("FCM 토큰 없음 - user_id=%s, 알림 건너뜀", user_id)
            return False

        try:
            self._get_app()
            from firebase_admin import messaging

            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={k: str(v) for k, v in (data or {}).items()},
                token=token,
            )
            message_id = messaging.send(message)
            logger.info("알림 발송 완료 - user_id=%s, message_id=%s", user_id, message_id)
            return True
        except Exception:
            logger.exception("알림 발송 실패 - user_id=%s", user_id)
            return False


notification_service = NotificationService()
