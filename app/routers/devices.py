import logging

from fastapi import APIRouter, Depends

from app.schemas.device import DeviceRegisterRequest, DeviceRegisterResponse
from app.services.auth_service import get_current_user
from app.services.notification_service import notification_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/register", response_model=DeviceRegisterResponse)
def register_device(request: DeviceRegisterRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    logger.info("디바이스 등록 - user_id=%s", user_id)
    notification_service.register_token(user_id, request.fcm_token)
    return DeviceRegisterResponse(message="Device registered")
