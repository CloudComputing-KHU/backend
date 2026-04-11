from typing import List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from app.schemas.question import QuestionType
from app.schemas.answer import AnswerRequest, AnswerResponse, AnswerItem
from app.services.question_service import question_service
from app.services.ai_service import ai_service

router = APIRouter()

@router.get("/{type}", response_model=List[AnswerItem])
def get_user_answers(type: QuestionType, user_id: str):
    return question_service.get_user_answers(type, user_id)

@router.post("/{type}", response_model=AnswerResponse)
def submit_answer(type: QuestionType, request: AnswerRequest):
    if not question_service.save_answer(type, request):
        raise HTTPException(status_code=400, detail="답변 저장 실패")
        
    return AnswerResponse(success=True, message="Success")

@router.post("/{type}/voice", response_model=AnswerResponse)
def submit_voice_answer(
    type: QuestionType,
    background_tasks: BackgroundTasks,
    user_id: str = Form(...),
    question_id: str = Form(...) ,
    file: UploadFile = File(...)
):
    valid_ext = (".mp3", ".wav", ".m4a")
    if not file.filename.lower().endswith(valid_ext):
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

    return AnswerResponse(success=True, message="Voice uploaded")
