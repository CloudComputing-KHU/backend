import logging

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.family import (
    FamilyConnectRequest,
    FamilyInviteResponse,
    FamilyLinkResponse,
    FamilyMeResponse,
)
from app.services.auth_service import get_current_user
from app.services.family_service import family_service, get_role_from_claims, require_role

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/invites", response_model=FamilyInviteResponse)
def create_family_invite(current_user: dict = Depends(get_current_user)):
    require_role(current_user, "child")
    child_user_id = current_user["sub"]
    logger.info("가족 초대 코드 생성 - child_user_id=%s", child_user_id)

    invite_record = family_service.create_invite(child_user_id)

    return FamilyInviteResponse(
        message="가족 연결 초대 코드가 준비됐습니다.",
        invite_code=invite_record["invite_code"],
        child_user_id=invite_record["child_user_id"],
        status=invite_record["status"],
        created_at=invite_record["created_at"],
        expires_at=invite_record["expires_at"],
    )


@router.post("/connect", response_model=FamilyLinkResponse)
def connect_family(
    request: FamilyConnectRequest,
    current_user: dict = Depends(get_current_user),
):
    require_role(current_user, "parent")
    parent_user_id = current_user["sub"]
    logger.info(
        "가족 연결 요청 - parent_user_id=%s, invite_code=%s",
        parent_user_id,
        request.invite_code,
    )

    link_record = family_service.connect_parent(parent_user_id, request.invite_code)

    return FamilyLinkResponse(
        message="가족 연결이 완료됐습니다.",
        link_id=link_record["link_id"],
        parent_user_id=link_record["parent_user_id"],
        child_user_id=link_record["child_user_id"],
        status=link_record["status"],
        connected_at=link_record["connected_at"],
    )


@router.get("/me", response_model=FamilyMeResponse)
def get_my_family(current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    role = get_role_from_claims(current_user)
    logger.info("가족 연결 상태 조회 - user_id=%s", user_id)
    return family_service.get_my_family(user_id=user_id, role=role)
