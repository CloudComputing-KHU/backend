from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from app.schemas.photo import PhotoResponse
from app.services.photo_service import photo_service

router = APIRouter()

@router.post("", response_model=PhotoResponse)
def upload_photo(
    sender_user_id: str = Form(...),
    receiver_user_id: str = Form(...),
    caption: Optional[str] = Form(None),
    scheduled_at: Optional[datetime] = Form(None),
    file: UploadFile = File(...)
):
    valid_ext = (".jpg", ".jpeg", ".png")
    if not file.filename.lower().endswith(valid_ext):
        raise HTTPException(status_code=400, detail="Invalid extension")
        
    # TODO: S3 연동
    mock_s3_url = f"s3://my-virtual-bucket/photos/{sender_user_id}/{file.filename}"
    
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
