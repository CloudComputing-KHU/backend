import asyncio
import io
import logging
import uuid
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from PIL import Image, ImageOps
from app.schemas.photo import PhotoResponse
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

@router.post("", response_model=PhotoResponse)
async def upload_photo(
    sender_user_id: str = Form(...),
    receiver_user_id: str = Form(...),
    caption: Optional[str] = Form(None),
    scheduled_at: Optional[datetime] = Form(None),
    file: UploadFile = File(...)
):
    logger.info("사진 업로드 - sender=%s, receiver=%s, filename=%s", sender_user_id, receiver_user_id, file.filename)

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
        receiver_user_id=receiver_user_id,
        file_path=s3_path,
        caption=caption,
        scheduled_at=scheduled_at,
    )

    if scheduled_at:
        asyncio.create_task(photo_service.schedule_dispatch(photo_record))
        logger.info("예약 사진 등록 - photo_id=%s, scheduled_at=%s", photo_record["photo_id"], scheduled_at)

    return {**photo_record, "presigned_url": storage_service.generate_presigned_url(s3_path)}

@router.get("/history", response_model=List[PhotoResponse])
def get_photo_history(user_id: str):
    logger.info("사진 내역 조회 - user_id=%s", user_id)
    photos = photo_service.get_photo_history(user_id)
    return [{**p, "presigned_url": storage_service.generate_presigned_url(p["image_url"])} for p in photos]


@router.get("/received", response_model=List[PhotoResponse])
def get_received_photos(user_id: str):
    logger.info("수신 사진 조회 - user_id=%s", user_id)
    photos = photo_service.get_received_photos(user_id)
    return [{**p, "presigned_url": storage_service.generate_presigned_url(p["image_url"])} for p in photos]
