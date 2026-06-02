import asyncio
import io
import logging
import os
import uuid
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from PIL import Image, ImageOps
from app.schemas.photo import PhotoResponse, QuickReactionRequest, ReactionResponse
from app.services.auth_service import get_current_user
from app.services.family_service import family_service, get_role_from_claims
from app.services.notification_service import notification_service
from app.services.photo_service import photo_service
from app.services.storage_service import storage_service

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_DIMENSION = 1280
JPEG_QUALITY = 85

def _compress_image(contents: bytes) -> tuple[bytes, str]:
    """이미지를 리사이즈하고 압축. 투명도 있으면 PNG, 없으면 JPEG로 변환."""
    img = Image.open(io.BytesIO(contents))
    img = ImageOps.exif_transpose(img)  # EXIF 회전 보정

    w, h = img.size
    if max(w, h) > MAX_DIMENSION:
        ratio = MAX_DIMENSION / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    has_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )

    out = io.BytesIO()
    if has_alpha:
        img.save(out, format="PNG", optimize=True)
        return out.getvalue(), ".png"
    else:
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return out.getvalue(), ".jpeg"


def _resolve_photo_receiver_user_id(current_user: dict) -> str:
    user_id = current_user["sub"]
    role = get_role_from_claims(current_user)
    linked_user_id = family_service.require_linked_user_id(user_id)
    logger.info(
        "사진 수신자 결정 - sender=%s, role=%s, resolved_receiver=%s",
        user_id,
        role,
        linked_user_id,
    )
    return linked_user_id

@router.post("", response_model=PhotoResponse)
async def upload_photo(
    caption: Optional[str] = Form(None),
    scheduled_at: Optional[datetime] = Form(None),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    sender_user_id = current_user["sub"]
    resolved_receiver_user_id = _resolve_photo_receiver_user_id(current_user)
    logger.info(
        "사진 업로드 - sender=%s, receiver=%s, filename=%s",
        sender_user_id,
        resolved_receiver_user_id,
        file.filename,
    )

    valid_ext = (".jpg", ".jpeg", ".png")
    if not file.filename.lower().endswith(valid_ext):
        logger.warning("유효하지 않은 파일 확장자 - filename=%s", file.filename)
        raise HTTPException(status_code=400, detail="Invalid extension")

    original_contents = await file.read()
    compressed_contents, new_ext = _compress_image(original_contents)

    new_filename = uuid.uuid4().hex + new_ext
    logger.info("사진 압축 완료 - 저장 파일명=%s", new_filename)

    content_type = "image/png" if new_ext == ".png" else "image/jpeg"
    s3_path = storage_service.upload_photo(
        user_id=sender_user_id,
        stored_filename=new_filename,
        contents=compressed_contents,
        content_type=content_type,
    )

    photo_record = photo_service.save_photo(
        sender_user_id=sender_user_id,
        receiver_user_id=resolved_receiver_user_id,
        file_path=s3_path,
        caption=caption,
        scheduled_at=scheduled_at,
    )

    if photo_record["status"] == "scheduled":
        asyncio.create_task(photo_service.schedule_dispatch(photo_record))
        logger.info("예약 사진 등록 - photo_id=%s, scheduled_at=%s", photo_record["photo_id"], scheduled_at)
    else:
        notification_service.send(
            user_id=resolved_receiver_user_id,
            title="새 사진이 도착했어요",
            body=caption or "가족이 사진을 보냈어요.",
            data={"photo_id": photo_record["photo_id"], "type": "photo_received"},
        )

    return {**photo_record, "presigned_url": storage_service.generate_presigned_url(s3_path)}

@router.get("/history", response_model=List[PhotoResponse])
def get_photo_history(current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    logger.info("사진 내역 조회 - user_id=%s", user_id)
    photos = photo_service.get_photo_history(user_id)
    return [{**p, "presigned_url": storage_service.generate_presigned_url(p["image_url"])} for p in photos]


@router.get("/received/history", response_model=List[PhotoResponse])
def get_received_photos_history(current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    logger.info("수신 사진 전체 조회 - user_id=%s", user_id)
    photos = photo_service.get_received_photos_history(user_id)
    return [{**p, "presigned_url": storage_service.generate_presigned_url(p["image_url"])} for p in photos]

@router.get("/received", response_model=List[PhotoResponse])
def get_received_photos(current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    logger.info("수신 사진 조회 - user_id=%s", user_id)
    photos = photo_service.get_received_photos(user_id)
    return [{**p, "presigned_url": storage_service.generate_presigned_url(p["image_url"])} for p in photos]


@router.get("/{photo_id}/reactions", response_model=List[ReactionResponse])
def get_reactions(
    photo_id: str,
    current_user: dict = Depends(get_current_user),
):
    logger.info("반응 조회 - photo_id=%s", photo_id)
    reactions = photo_service.get_reactions(photo_id)
    return [
        {**r, "presigned_url": storage_service.generate_presigned_url(r["voice_url"]) if r["voice_url"] else None}
        for r in reactions
    ]


@router.post("/{photo_id}/reactions/quick", response_model=ReactionResponse)
def save_quick_reaction(
    photo_id: str,
    request: QuickReactionRequest,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["sub"]
    logger.info("빠른 반응 저장 - photo_id=%s, user_id=%s, label=%s", photo_id, user_id, request.label)
    record = photo_service.save_reaction(
        photo_id=photo_id,
        user_id=user_id,
        reaction_type="quick",
        label=request.label,
    )
    photo = photo_service.get_photo(photo_id)
    if photo:
        notification_service.send(
            user_id=photo["sender_user_id"],
            title="사진에 반응이 왔어요",
            body=f"가족이 사진에 반응했어요: {request.label}",
            data={"photo_id": photo_id, "type": "photo_reaction"},
        )
    return {**record, "presigned_url": None}


@router.post("/{photo_id}/reactions/voice", response_model=ReactionResponse)
async def save_voice_reaction(
    photo_id: str,
    duration_seconds: Optional[int] = Form(None),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["sub"]
    logger.info("음성 반응 저장 - photo_id=%s, user_id=%s, filename=%s", photo_id, user_id, file.filename)

    valid_ext = (".m4a", ".wav", ".mp3")
    if not file.filename.lower().endswith(valid_ext):
        raise HTTPException(status_code=400, detail="m4a, wav, mp3 파일만 업로드할 수 있습니다.")

    contents = await file.read()
    stored_filename = uuid.uuid4().hex + os.path.splitext(file.filename)[1].lower()
    voice_url = storage_service.upload_voice(
        user_id=user_id,
        stored_filename=stored_filename,
        contents=contents,
        content_type=file.content_type,
    )
    record = photo_service.save_reaction(
        photo_id=photo_id,
        user_id=user_id,
        reaction_type="voice",
        voice_url=voice_url,
        duration_seconds=duration_seconds,
    )
    photo = photo_service.get_photo(photo_id)
    if photo:
        notification_service.send(
            user_id=photo["sender_user_id"],
            title="사진에 음성 반응이 왔어요",
            body="가족이 사진에 음성으로 반응했어요.",
            data={"photo_id": photo_id, "type": "photo_reaction"},
        )
    return {**record, "presigned_url": storage_service.generate_presigned_url(voice_url)}
