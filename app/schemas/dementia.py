from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Literal


DementiaAnalysisStatus = Literal[
    "pending",          # 분석 요청 접수됨
    "transcribing",     # Transcribe 변환 중
    "transcribed",      # 텍스트 변환 완료
    "analyzing",        # Bedrock 분석 중
    "completed",        # 분석 완료
    "failed",           # 분석 실패
]

RiskLevel = Literal["low", "medium", "high"]


class DementiaAnalysisRequest(BaseModel):
    """치매 위험 분석 요청 — 이미 S3에 업로드된 음성의 answer_id를 지정"""
    user_id: str
    answer_id: str


class DementiaAnalysisResponse(BaseModel):
    """분석 요청 접수 응답"""
    message: str
    analysis_id: str
    answer_id: str
    user_id: str
    status: DementiaAnalysisStatus
    created_at: datetime


class DementiaAnalysisResult(BaseModel):
    """분석 완료 결과 조회용"""
    analysis_id: str
    answer_id: str
    user_id: str
    status: DementiaAnalysisStatus
    transcript: Optional[str] = None
    risk_level: Optional[RiskLevel] = None
    risk_score: Optional[float] = None
    analysis_summary: Optional[str] = None
    indicators: Optional[list[str]] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class DementiaAnalysisItem(BaseModel):
    """분석 목록 조회용"""
    analysis_id: str
    answer_id: str
    user_id: str
    status: DementiaAnalysisStatus
    risk_level: Optional[RiskLevel] = None
    risk_score: Optional[float] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
