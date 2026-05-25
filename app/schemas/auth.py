from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel


class SignUpRequest(BaseModel):
    role: Literal["child", "parent"]
    name: str
    email: str
    password: str
    password_confirm: str

    def validate_passwords_match(self):
        if self.password != self.password_confirm:
            raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")


class SignUpResponse(BaseModel):
    message: str


class ConfirmRequest(BaseModel):
    email: str
    confirmation_code: str


class ConfirmResponse(BaseModel):
    message: str


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    id_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    id_token: str
    expires_in: int
    token_type: str = "Bearer"


class LogoutRequest(BaseModel):
    access_token: str
