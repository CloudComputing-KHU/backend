from fastapi import APIRouter, HTTPException
from app.schemas.question import Question, QuestionType
from app.services.question_service import question_service

router = APIRouter()

@router.get("/{type}", response_model=Question)
def get_question(type: QuestionType):
    question = question_service.get_todays_question(type)
    if not question:
        raise HTTPException(status_code=404, detail="해당 타입의 질문을 찾을 수 없습니다.")
    
    return question
