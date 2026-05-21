import logging
from typing import List

from fastapi import APIRouter, Depends

from app.schemas.notification import NotificationItem
from app.services.auth_service import get_current_user
from app.services.notification_service import notification_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=List[NotificationItem])
def get_notifications(current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    logger.info("알림 내역 조회 - user_id=%s", user_id)
    return notification_service.get_notifications(user_id)
