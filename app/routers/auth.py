import logging

from fastapi import APIRouter

from app.schemas.auth import (
    ConfirmRequest,
    ConfirmResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    SignUpRequest,
    SignUpResponse,
)
from app.services.auth_service import auth_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/signup", response_model=SignUpResponse)
def sign_up(request: SignUpRequest):
    logger.info("회원가입 요청 - email=%s, role=%s", request.email, request.role)
    request.validate_passwords_match()
    auth_service.sign_up(
        role=request.role,
        name=request.name,
        email=request.email,
        password=request.password,
    )
    return SignUpResponse(message="인증 이메일을 확인해주세요.")


@router.post("/confirm", response_model=ConfirmResponse)
def confirm(request: ConfirmRequest):
    logger.info("이메일 인증 요청 - email=%s", request.email)
    auth_service.confirm_sign_up(request.email, request.confirmation_code)
    return ConfirmResponse(message="가입이 완료됐습니다.")


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest):
    logger.info("로그인 요청 - email=%s", request.email)
    result = auth_service.login(request.email, request.password)
    return LoginResponse(**result)


@router.post("/refresh", response_model=RefreshResponse)
def refresh(request: RefreshRequest):
    result = auth_service.refresh(request.refresh_token)
    return RefreshResponse(**result)
