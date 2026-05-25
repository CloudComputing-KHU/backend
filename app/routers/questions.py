import logging
from fastapi import APIRouter, Depends, HTTPException
from app.schemas.question import DailyQuestionProgress, Question, QuestionType
from app.services.auth_service import get_current_user
from app.services.question_service import question_service

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/status/today", response_model=DailyQuestionProgress)
def get_today_question_status(current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    logger.info("오늘의 질문 진행 상태 조회 - user_id=%s", user_id)
    return question_service.get_daily_progress(user_id)

@router.get("/{type}", response_model=Question)
def get_question(type: QuestionType):
    logger.info("오늘의 질문 조회 - type=%s", type)
    question = question_service.get_todays_question(type)
    if not question:
        logger.warning("질문 없음 - type=%s", type)
        raise HTTPException(status_code=404, detail="해당 타입의 질문을 찾을 수 없습니다.")
    return question
