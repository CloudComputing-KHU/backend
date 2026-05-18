"""
Firebase Admin SDK 기반 FCM 푸시 알림 서비스
- 디바이스 토큰 등록/조회 (in-memory, 향후 DynamoDB 연동)
- Firebase를 통해 Android/iOS 알림 발송
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# user_id → fcm_token 매핑 (향후 DynamoDB 연동)
_device_tokens: dict[str, str] = {}


class NotificationService:
    def __init__(self) -> None:
        self._app = None

    def _get_app(self):
        """Firebase Admin SDK 초기화 (lazy, 1회)"""
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
        _device_tokens[user_id] = fcm_token
        logger.info("FCM 토큰 등록 - user_id=%s", user_id)

    def get_token(self, user_id: str) -> Optional[str]:
        return _device_tokens.get(user_id)

    def send(self, user_id: str, title: str, body: str, data: Optional[dict] = None) -> bool:
        """user_id 디바이스로 푸시 알림 발송. 성공 여부 반환."""
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
