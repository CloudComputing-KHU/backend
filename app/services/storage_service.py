import mimetypes
import os
from dataclasses import dataclass
import logging

import boto3
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    PartialCredentialsError,
)
from dotenv import load_dotenv
from fastapi import HTTPException


load_dotenv()
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class S3Config:
    region: str
    bucket_name: str
    voice_prefix: str
    photo_prefix: str
    url_mode: str


class StorageService:
    def __init__(self) -> None:
        self._client = None

    def _load_config(self) -> S3Config:
        region = os.getenv("AWS_REGION")
        bucket_name = os.getenv("S3_BUCKET_NAME")
        voice_prefix = os.getenv("S3_VOICE_PREFIX")
        photo_prefix = os.getenv("S3_PHOTO_PREFIX")
        url_mode = os.getenv("S3_URL_MODE", "s3_uri")

        missing = [
            name
            for name, value in (
                ("AWS_REGION", region),
                ("S3_BUCKET_NAME", bucket_name),
                ("S3_VOICE_PREFIX", voice_prefix),
                ("S3_PHOTO_PREFIX", photo_prefix),
            )
            if not value
        ]
        if missing:
            logger.error("S3 설정 누락 - missing=%s", ",".join(missing))
            raise HTTPException(
                status_code=500,
                detail=f"Missing S3 configuration: {', '.join(missing)}",
            )

        return S3Config(
            region=region,
            bucket_name=bucket_name,
            voice_prefix=voice_prefix.strip("/"),
            photo_prefix=photo_prefix.strip("/"),
            url_mode=url_mode,
        )

    def _client_for(self):
        if self._client is None:
            self._client = boto3.client("s3")
        return self._client

    @staticmethod
    def _build_key(prefix: str, owner_id: str, filename: str) -> str:
        return f"{prefix}/{owner_id}/{filename}"

    @staticmethod
    def _guess_content_type(filename: str, content_type: str | None) -> str:
        if content_type:
            return content_type
        guessed, _ = mimetypes.guess_type(filename)
        return guessed or "application/octet-stream"

    @staticmethod
    def _to_response_path(config: S3Config, key: str) -> str:
        if config.url_mode == "https":
            return f"https://{config.bucket_name}.s3.{config.region}.amazonaws.com/{key}"
        return f"s3://{config.bucket_name}/{key}"

    def upload_voice(self, user_id: str, stored_filename: str, contents: bytes, content_type: str | None) -> str:
        config = self._load_config()
        key = self._build_key(config.voice_prefix, user_id, stored_filename)
        self._upload_object(config, key, contents, content_type, stored_filename)
        return self._to_response_path(config, key)

    def upload_photo(self, user_id: str, stored_filename: str, contents: bytes, content_type: str | None) -> str:
        config = self._load_config()
        key = self._build_key(config.photo_prefix, user_id, stored_filename)
        self._upload_object(config, key, contents, content_type, stored_filename)
        return self._to_response_path(config, key)

    def _upload_object(
        self,
        config: S3Config,
        key: str,
        contents: bytes,
        content_type: str | None,
        filename: str,
    ) -> None:
        resolved_content_type = self._guess_content_type(filename, content_type)
        logger.info(
            "S3 업로드 시작 - bucket=%s, key=%s, content_type=%s, size=%s",
            config.bucket_name,
            key,
            resolved_content_type,
            len(contents),
        )
        try:
            self._client_for().put_object(
                Bucket=config.bucket_name,
                Key=key,
                Body=contents,
                ContentType=resolved_content_type,
            )
            logger.info("S3 업로드 성공 - bucket=%s, key=%s", config.bucket_name, key)
        except NoCredentialsError as exc:
            logger.exception("AWS 자격 증명 없음 - bucket=%s, key=%s", config.bucket_name, key)
            raise HTTPException(status_code=500, detail="Missing AWS credentials") from exc
        except PartialCredentialsError as exc:
            logger.exception("AWS 자격 증명 불완전 - bucket=%s, key=%s", config.bucket_name, key)
            raise HTTPException(status_code=500, detail="Incomplete AWS credentials") from exc
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            logger.exception(
                "S3 클라이언트 오류 - bucket=%s, key=%s, error_code=%s",
                config.bucket_name,
                key,
                error_code,
            )
            raise HTTPException(
                status_code=502,
                detail=f"S3 upload failed: {error_code}",
            ) from exc
        except BotoCoreError as exc:
            logger.exception("S3 업로드 코어 오류 - bucket=%s, key=%s", config.bucket_name, key)
            raise HTTPException(status_code=502, detail="S3 upload failed") from exc


    def generate_presigned_url(self, s3_uri: str, expiration: int = 604800) -> str | None:
        """s3:// URI를 Presigned URL로 변환한다. 최대 유효기간 7일."""
        if not s3_uri or not s3_uri.startswith("s3://"):
            return None
        without_scheme = s3_uri[5:]
        bucket, _, key = without_scheme.partition("/")
        try:
            return self._client_for().generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expiration,
            )
        except (NoCredentialsError, PartialCredentialsError, ClientError, BotoCoreError) as exc:
            logger.exception("Presigned URL 생성 실패 - s3_uri=%s", s3_uri)
            raise HTTPException(status_code=502, detail=f"Failed to generate presigned URL: {exc}") from exc


storage_service = StorageService()
