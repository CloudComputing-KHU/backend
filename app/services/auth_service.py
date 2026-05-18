"""
AWS Cognito 기반 인증 서비스
- 회원가입, 이메일 인증, 로그인, 토큰 갱신
- JWT(ID 토큰) 검증 및 현재 사용자 추출
"""

import json
import logging
import os
import urllib.request

import boto3
from botocore.exceptions import ClientError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import jwt
from jwt.algorithms import RSAAlgorithm

logger = logging.getLogger(__name__)

security = HTTPBearer()


class AuthService:
    def __init__(self) -> None:
        self._client = None
        self._jwks: dict | None = None

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client(
                "cognito-idp",
                region_name=os.getenv("AWS_REGION", "ap-northeast-2"),
            )
        return self._client

    @property
    def _user_pool_id(self) -> str:
        return os.getenv("COGNITO_USER_POOL_ID", "")

    @property
    def _app_client_id(self) -> str:
        return os.getenv("COGNITO_APP_CLIENT_ID", "")

    # ── 회원가입 ──

    def sign_up(self, role: str, name: str, email: str, password: str) -> dict:
        try:
            resp = self._get_client().sign_up(
                ClientId=self._app_client_id,
                Username=email,
                Password=password,
                UserAttributes=[
                    {"Name": "name", "Value": name},
                    {"Name": "email", "Value": email},
                    {"Name": "custom:role", "Value": role},
                ],
            )
            return {"user_sub": resp["UserSub"]}
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "UsernameExistsException":
                raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다.")
            if code == "InvalidPasswordException":
                raise HTTPException(status_code=400, detail="비밀번호가 요구사항을 충족하지 않습니다.")
            raise HTTPException(status_code=400, detail=e.response["Error"]["Message"])

    # ── 이메일 인증 ──

    def confirm_sign_up(self, email: str, confirmation_code: str) -> None:
        try:
            self._get_client().confirm_sign_up(
                ClientId=self._app_client_id,
                Username=email,
                ConfirmationCode=confirmation_code,
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "CodeMismatchException":
                raise HTTPException(status_code=400, detail="인증 코드가 올바르지 않습니다.")
            if code == "ExpiredCodeException":
                raise HTTPException(status_code=400, detail="인증 코드가 만료됐습니다.")
            raise HTTPException(status_code=400, detail=e.response["Error"]["Message"])

    # ── 로그인 ──

    def login(self, email: str, password: str) -> dict:
        try:
            resp = self._get_client().initiate_auth(
                ClientId=self._app_client_id,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": email, "PASSWORD": password},
            )
            result = resp["AuthenticationResult"]
            return {
                "access_token": result["AccessToken"],
                "id_token": result["IdToken"],
                "refresh_token": result["RefreshToken"],
                "expires_in": result["ExpiresIn"],
            }
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("NotAuthorizedException", "UserNotFoundException"):
                raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
            if code == "UserNotConfirmedException":
                raise HTTPException(status_code=403, detail="이메일 인증이 완료되지 않았습니다.")
            raise HTTPException(status_code=400, detail=e.response["Error"]["Message"])

    # ── 토큰 갱신 ──

    def refresh(self, refresh_token: str) -> dict:
        try:
            resp = self._get_client().initiate_auth(
                ClientId=self._app_client_id,
                AuthFlow="REFRESH_TOKEN_AUTH",
                AuthParameters={"REFRESH_TOKEN": refresh_token},
            )
            result = resp["AuthenticationResult"]
            return {
                "access_token": result["AccessToken"],
                "id_token": result["IdToken"],
                "expires_in": result["ExpiresIn"],
            }
        except ClientError as e:
            raise HTTPException(status_code=401, detail="토큰 갱신에 실패했습니다.")

    # ── JWT 검증 ──

    def _get_jwks(self) -> dict:
        if self._jwks is None:
            region = os.getenv("AWS_REGION", "ap-northeast-2")
            url = (
                f"https://cognito-idp.{region}.amazonaws.com"
                f"/{self._user_pool_id}/.well-known/jwks.json"
            )
            with urllib.request.urlopen(url) as resp:
                self._jwks = json.loads(resp.read())
        return self._jwks

    def verify_token(self, token: str) -> dict:
        try:
            kid = jwt.get_unverified_header(token)["kid"]
            jwks = self._get_jwks()
            key_data = next((k for k in jwks["keys"] if k["kid"] == kid), None)
            if not key_data:
                raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

            public_key = RSAAlgorithm.from_jwk(json.dumps(key_data))
            region = os.getenv("AWS_REGION", "ap-northeast-2")
            issuer = f"https://cognito-idp.{region}.amazonaws.com/{self._user_pool_id}"

            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                issuer=issuer,
                audience=self._app_client_id,
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="토큰이 만료됐습니다.")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")


auth_service = AuthService()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Authorization: Bearer <id_token> 헤더에서 사용자 정보를 추출하는 의존성."""
    return auth_service.verify_token(credentials.credentials)
