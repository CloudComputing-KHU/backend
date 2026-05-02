"""
치매 위험 감지 API 라우터
- POST /dementia/analyze      : 음성 답변에 대한 치매 위험 분석 요청
- GET  /dementia/{analysis_id} : 분석 결과 단건 조회
- GET  /dementia?user_id=...   : 사용자별 분석 이력 조회
"""

import logging
from typing import List

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.schemas.dementia import (
    DementiaAnalysisItem,
    DementiaAnalysisRequest,
    DementiaAnalysisResponse,
    DementiaAnalysisResult,
)
from app.services.dementia_service import dementia_service
from app.services.question_service import mock_answers

router = APIRouter()
logger = logging.getLogger(__name__)


def _find_answer(answer_id: str, user_id: str) -> dict:
    """in-memory 답변 목록에서 해당 음성 답변을 찾는다."""
    for ans in mock_answers:
        if ans["answer_id"] == answer_id and ans["user_id"] == user_id:
            return ans
    raise HTTPException(
        status_code=404,
        detail=f"answer_id={answer_id}에 해당하는 음성 답변을 찾을 수 없습니다.",
    )


@router.post("/analyze", response_model=DementiaAnalysisResponse)
async def request_dementia_analysis(
    request: DementiaAnalysisRequest,
    background_tasks: BackgroundTasks,
):
    """
    이미 업로드된 음성 답변(answer_id)에 대해 치매 위험 분석을 요청합니다.
    S3에 저장된 음성 → Transcribe STT → Bedrock 분석 파이프라인이 백그라운드에서 실행됩니다.
    """
    logger.info(
        "치매 분석 요청 - user_id=%s, answer_id=%s",
        request.user_id,
        request.answer_id,
    )

    # 1. 음성 답변 레코드 확인
    answer_record = _find_answer(request.answer_id, request.user_id)

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
        user_id=request.user_id,
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
        user_id=analysis_record["user_id"],
        status=analysis_record["status"],
        created_at=analysis_record["created_at"],
    )


@router.get("/{analysis_id}", response_model=DementiaAnalysisResult)
def get_dementia_analysis(analysis_id: str):
    """분석 결과 단건 조회 — 진행 중이면 현재 status를, 완료 시 전체 결과를 반환합니다."""
    logger.info("치매 분석 결과 조회 - analysis_id=%s", analysis_id)

    record = dementia_service.get_analysis(analysis_id)
    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"analysis_id={analysis_id}에 해당하는 분석을 찾을 수 없습니다.",
        )

    return DementiaAnalysisResult(**record)


@router.get("", response_model=List[DementiaAnalysisItem])
def get_user_analyses(user_id: str):
    """사용자별 치매 분석 이력을 최신순으로 조회합니다."""
    logger.info("치매 분석 이력 조회 - user_id=%s", user_id)
    return dementia_service.get_user_analyses(user_id)
