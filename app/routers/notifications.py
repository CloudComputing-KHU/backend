import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException

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


@router.get("/unread", response_model=List[NotificationItem])
def get_unread_notifications(current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    logger.info("미읽음 알림 조회 - user_id=%s", user_id)
    return notification_service.get_unread_notifications(user_id)


@router.patch("/read-all")
def mark_all_notifications_read(current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    logger.info("알림 전체 읽음 처리 - user_id=%s", user_id)
    notification_service.mark_all_read(user_id)
    return {"message": "전체 읽음 처리 완료"}


@router.patch("/{notification_id}/read")
def mark_notification_read(notification_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    logger.info("알림 읽음 처리 - notification_id=%s, user_id=%s", notification_id, user_id)
    found = notification_service.mark_read(notification_id, user_id)
    if not found:
        raise HTTPException(status_code=404, detail="해당 알림을 찾을 수 없습니다.")
    return {"message": "읽음 처리 완료"}
