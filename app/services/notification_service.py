import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from boto3.dynamodb.conditions import Attr, Key

from app.services.dynamodb_service import dynamodb_service, _convert_decimals

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


class DynamoDBNotificationBackend:
    @property
    def device_tokens_table(self) -> str:
        return os.getenv("DYNAMODB_DEVICE_TOKENS_TABLE", "device_tokens")

    @property
    def notifications_table(self) -> str:
        return os.getenv("DYNAMODB_NOTIFICATIONS_TABLE", "notifications")

    @staticmethod
    def is_configured() -> bool:
        return dynamodb_service.is_configured()

    def register_token(self, user_id: str, fcm_token: str) -> None:
        dynamodb_service.table(self.device_tokens_table).put_item(Item={
            "user_id": user_id,
            "fcm_token": fcm_token,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    def get_token(self, user_id: str) -> Optional[str]:
        resp = dynamodb_service.table(self.device_tokens_table).get_item(Key={"user_id": user_id})
        item = resp.get("Item")
        return item.get("fcm_token") if item else None

    def save_notification(self, user_id: str, title: str, body: str, data: Optional[dict]) -> dict:
        record: dict = {
            "notification_id": uuid.uuid4().hex,
            "user_id": user_id,
            "title": title,
            "body": body,
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if data:
            record["data"] = data
        dynamodb_service.table(self.notifications_table).put_item(Item=record)
        return record

    def get_notifications(self, user_id: str) -> list[dict]:
        resp = dynamodb_service.table(self.notifications_table).query(
            KeyConditionExpression=Key("user_id").eq(user_id),
        )
        items = [_convert_decimals(item) for item in resp.get("Items", [])]
        return sorted(items, key=lambda x: x.get("created_at", ""), reverse=True)

    def get_unread_notifications(self, user_id: str) -> list[dict]:
        resp = dynamodb_service.table(self.notifications_table).query(
            KeyConditionExpression=Key("user_id").eq(user_id),
            FilterExpression=Attr("is_read").eq(False),
        )
        items = [_convert_decimals(item) for item in resp.get("Items", [])]
        return sorted(items, key=lambda x: x.get("created_at", ""), reverse=True)

    def mark_read(self, notification_id: str, user_id: str) -> bool:
        table = dynamodb_service.table(self.notifications_table)
        resp = table.get_item(Key={"user_id": user_id, "notification_id": notification_id})
        if not resp.get("Item"):
            return False
        table.update_item(
            Key={"user_id": user_id, "notification_id": notification_id},
            UpdateExpression="SET #ir = :ir",
            ExpressionAttributeNames={"#ir": "is_read"},
            ExpressionAttributeValues={":ir": True},
        )
        return True

    def mark_all_read(self, user_id: str) -> None:
        table = dynamodb_service.table(self.notifications_table)
        resp = table.query(
            KeyConditionExpression=Key("user_id").eq(user_id),
            FilterExpression=Attr("is_read").eq(False),
        )
        with table.batch_writer() as batch:
            for item in resp.get("Items", []):
                item = dict(item)
                item["is_read"] = True
                batch.put_item(Item=item)


class NotificationService:
    def __init__(self) -> None:
        self._app = None
        self._memory_backend = InMemoryNotificationBackend()
        self._dynamodb_backend = DynamoDBNotificationBackend()
        self._backend_override = None

    def set_backend(self, backend) -> None:
        self._backend_override = backend

    def reset_backend(self) -> None:
        self._backend_override = None

    def _backend(self):
        if self._backend_override is not None:
            return self._backend_override
        if self._dynamodb_backend.is_configured():
            return self._dynamodb_backend
        if os.getenv("ALLOW_IN_MEMORY_FALLBACK", "").lower() == "true":
            return self._memory_backend
        raise HTTPException(
            status_code=500,
            detail="DynamoDB is not configured for notification persistence.",
        )

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
