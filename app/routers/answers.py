import logging
import os
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from app.schemas.question import QuestionType
from app.schemas.answer import (
    AnswerItem,
    AnswerRequest,
    AnswerResponse,
    VoiceUploadResponse,
)
from app.services.auth_service import get_current_user
from app.services.notification_service import notification_service
from app.services.question_service import question_service
from app.services.storage_service import storage_service

router = APIRouter()
logger = logging.getLogger(__name__)

VALID_AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a")
VALID_AUDIO_CONTENT_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/x-m4a",
    "video/mp4",
}
MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024


def _prepare_audio_upload(file: UploadFile, contents: bytes) -> tuple[str, int, str | None]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    extension = os.path.splitext(file.filename)[1].lower()
    if extension not in VALID_AUDIO_EXTENSIONS:
        logger.warning("유효하지 않은 파일 확장자 - filename=%s", file.filename)
        raise HTTPException(status_code=400, detail="Invalid extension")

    file_size = len(contents)
    if file_size == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    if file_size > MAX_AUDIO_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File too large")

    content_type = file.content_type
    if content_type and content_type not in VALID_AUDIO_CONTENT_TYPES:
        logger.warning("유효하지 않은 MIME 타입 - content_type=%s", content_type)
        raise HTTPException(status_code=400, detail="Invalid content type")

    stored_filename = f"{uuid.uuid4().hex}{extension}"
    return stored_filename, file_size, content_type


@router.get("/{type}", response_model=List[AnswerItem])
def get_user_answers(type: QuestionType, current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    logger.info("답변 목록 조회 - type=%s, user_id=%s", type, user_id)
    answers = question_service.get_user_answers(type, user_id)
    for ans in answers:
        if ans.get("voice_file_key"):
            ans["voice_url"] = storage_service.generate_presigned_url(ans["voice_file_key"])
    return answers

@router.post("/{type}", response_model=AnswerResponse)
def submit_answer(type: QuestionType, request: AnswerRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    logger.info("텍스트 답변 저장 - type=%s, user_id=%s", type, user_id)
    question_service.save_answer(type, request, user_id)
    if request.receiver_user_id:
        notification_service.send(
            user_id=request.receiver_user_id,
            title="새 답변이 도착했어요",
            body="가족이 오늘의 질문에 답했어요.",
            data={"type": "answer_received", "question_type": type},
        )
    return AnswerResponse(message="Success")

@router.post("/{type}/voice", response_model=VoiceUploadResponse)
async def submit_voice_answer(
    type: QuestionType,
    question_id: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["sub"]
    logger.info("음성 답변 업로드 - type=%s, user_id=%s, filename=%s", type, user_id, file.filename)

    contents = await file.read()
    stored_filename, file_size, content_type = _prepare_audio_upload(file, contents)

    s3_path = storage_service.upload_voice(
        user_id=user_id,
        stored_filename=stored_filename,
        contents=contents,
        content_type=content_type,
    )

    answer_record = question_service.save_voice_answer_metadata(
        q_type=type,
        user_id=user_id,
        question_id=question_id,
        file_path=s3_path,
        original_filename=file.filename,
        stored_filename=stored_filename,
        content_type=content_type,
        file_size=file_size,
    )

    logger.info("음성 답변 저장 완료 - user_id=%s", user_id)

    return VoiceUploadResponse(
        message="Voice uploaded",
        answer_id=answer_record["answer_id"],
        voice_status=answer_record["voice_status"],
        voice_file_key=answer_record["voice_file_key"],
        voice_url=storage_service.generate_presigned_url(answer_record["voice_file_key"]),
        original_filename=answer_record["original_filename"],
        stored_filename=answer_record["stored_filename"],
        content_type=answer_record["content_type"],
        file_size=answer_record["file_size"],
        created_at=answer_record["created_at"],
    )
