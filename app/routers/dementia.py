"""
치매 위험 감지 API 라우터
- POST /dementia/analyze      : 음성 답변에 대한 치매 위험 분석 요청
- GET  /dementia/{analysis_id} : 분석 결과 단건 조회
- GET  /dementia?user_id=...   : 사용자별 분석 이력 조회
"""

import logging
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.schemas.dementia import (
    DementiaAnalysisItem,
    DementiaAnalysisRequest,
    DementiaAnalysisResponse,
    DementiaAnalysisResult,
)
from app.services.auth_service import get_current_user
from app.services.dementia_service import dementia_service
from app.services.family_service import family_service, get_role_from_claims
from app.services.question_service import question_service

router = APIRouter()
logger = logging.getLogger(__name__)


def _find_answer(answer_id: str, user_id: str) -> dict:
    answer = question_service.get_answer_by_id(answer_id)
    if answer and answer["user_id"] == user_id:
        return answer
    raise HTTPException(
        status_code=404,
        detail=f"answer_id={answer_id}에 해당하는 음성 답변을 찾을 수 없습니다.",
    )


def _resolve_analysis_owner_user_id(current_user: dict) -> str:
    user_id = current_user["sub"]
    role = get_role_from_claims(current_user)
    if role == "child":
        return family_service.require_linked_user_id(user_id)
    return user_id


@router.post("/analyze", response_model=DementiaAnalysisResponse)
async def request_dementia_analysis(
    request: DementiaAnalysisRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["sub"]
    logger.info("치매 분석 요청 - user_id=%s, answer_id=%s", user_id, request.answer_id)

    # 1. 음성 답변 레코드 확인
    answer_record = _find_answer(request.answer_id, user_id)

    if answer_record.get("answer_type") != "voice":
        raise HTTPException(
            status_code=400,
            detail="음성(voice) 타입의 답변만 분석할 수 있습니다.",
        )

    voice_file_key = answer_record.get("voice_file_key")
    if not voice_file_key:
        raise HTTPException(
            status_code=400,
            detail="음성 파일이 아직 업로드되지 않았습니다.",
        )

    # 2. 분석 레코드 생성
    analysis_record = dementia_service.create_analysis_record(
        user_id=user_id,
        answer_id=request.answer_id,
    )

    # 3. 백그라운드 파이프라인 시작
    background_tasks.add_task(
        dementia_service.run_analysis_pipeline,
        analysis_record,
        voice_file_key,
    )

    logger.info(
        "치매 분석 백그라운드 시작 - analysis_id=%s",
        analysis_record["analysis_id"],
    )

    return DementiaAnalysisResponse(
        message="치매 위험 분석이 요청되었습니다. 분석 완료까지 수 분이 소요될 수 있습니다.",
        analysis_id=analysis_record["analysis_id"],
        answer_id=analysis_record["answer_id"],
        user_id=user_id,
        status=analysis_record["status"],
        created_at=analysis_record["created_at"],
    )


@router.get("/{analysis_id}", response_model=DementiaAnalysisResult)
def get_dementia_analysis(
    analysis_id: str,
    current_user: dict = Depends(get_current_user),
):
    """분석 결과 단건 조회 — 진행 중이면 현재 status를, 완료 시 전체 결과를 반환합니다."""
    analysis_owner_user_id = _resolve_analysis_owner_user_id(current_user)
    logger.info(
        "치매 분석 결과 조회 - analysis_id=%s, analysis_owner_user_id=%s",
        analysis_id,
        analysis_owner_user_id,
    )

    record = dementia_service.get_analysis(analysis_id)
    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"analysis_id={analysis_id}에 해당하는 분석을 찾을 수 없습니다.",
        )
    if record["user_id"] != analysis_owner_user_id:
        raise HTTPException(status_code=403, detail="해당 분석 결과를 조회할 권한이 없습니다.")

    return DementiaAnalysisResult(**record)


@router.get("", response_model=List[DementiaAnalysisItem])
def get_user_analyses(current_user: dict = Depends(get_current_user)):
    caller_user_id = current_user["sub"]
    analysis_owner_user_id = _resolve_analysis_owner_user_id(current_user)
    logger.info(
        "치매 분석 이력 조회 - caller_user_id=%s, analysis_owner_user_id=%s",
        caller_user_id,
        analysis_owner_user_id,
    )
    return dementia_service.get_user_analyses(analysis_owner_user_id)
