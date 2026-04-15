import logging
from typing import List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from app.schemas.question import QuestionType
from app.schemas.answer import AnswerRequest, AnswerResponse, AnswerItem
from app.services.question_service import question_service
from app.services.ai_service import ai_service

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/{type}", response_model=List[AnswerItem])
def get_user_answers(type: QuestionType, user_id: str):
    logger.info("답변 목록 조회 - type=%s, user_id=%s", type, user_id)
    return question_service.get_user_answers(type, user_id)

@router.post("/{type}", response_model=AnswerResponse)
def submit_answer(type: QuestionType, request: AnswerRequest):
    logger.info("텍스트 답변 저장 - type=%s, user_id=%s", type, request.user_id)
    question_service.save_answer(type, request)
    return AnswerResponse(message="Success")

@router.post("/{type}/voice", response_model=AnswerResponse)
async def submit_voice_answer(
    type: QuestionType,
    background_tasks: BackgroundTasks,
    user_id: str = Form(...),
    question_id: str = Form(...),
    file: UploadFile = File(...)
):
    logger.info("음성 답변 업로드 - type=%s, user_id=%s, filename=%s", type, user_id, file.filename)

    valid_ext = (".mp3", ".wav", ".m4a")
    if not file.filename.lower().endswith(valid_ext):
        logger.warning("유효하지 않은 파일 확장자 - filename=%s", file.filename)
        raise HTTPException(status_code=400, detail="Invalid extension")

    # TODO: S3 연동
    mock_s3_url = f"s3://my-virtual-bucket/voices/{user_id}/{file.filename}"

    answer_record = question_service.save_voice_answer_metadata(
        q_type=type,
        user_id=user_id,
        question_id=question_id,
        file_path=mock_s3_url
    )

    background_tasks.add_task(ai_service.mock_ai_analysis_task, answer_record)
    logger.info("음성 답변 저장 완료, AI 분석 백그라운드 시작 - user_id=%s", user_id)

    return AnswerResponse(message="Voice uploaded")
