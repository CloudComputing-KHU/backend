import io
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from PIL import Image, ImageOps
from app.schemas.photo import PhotoResponse
from app.services.photo_service import photo_service

router = APIRouter()

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
    valid_ext = (".jpg", ".jpeg", ".png")
    if not file.filename.lower().endswith(valid_ext):
        raise HTTPException(status_code=400, detail="Invalid extension")

    contents = await file.read()
    _, new_ext = _compress_image(contents)

    base_name = file.filename.rsplit(".", 1)[0]
    new_filename = base_name + new_ext

    # TODO: S3 연동 시 압축된 bytes(_) 사용
    mock_s3_url = f"s3://my-virtual-bucket/photos/{sender_user_id}/{new_filename}"

    return photo_service.save_photo(
        sender_user_id=sender_user_id,
        receiver_user_id=receiver_user_id,
        file_path=mock_s3_url,
        caption=caption,
        scheduled_at=scheduled_at
    )

@router.get("/history", response_model=List[PhotoResponse])
def get_photo_history(user_id: str):
    return photo_service.get_photo_history(user_id)
