"""
치매 위험 감지 서비스
- S3에서 음성 파일을 참조
- AWS Transcribe로 음성→텍스트 변환
- Lambda + API Gateway (OpenAI GPT)로 치매 위험 분석
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
from fastapi import HTTPException

from app.services.notification_service import notification_service
from app.services.supabase_service import supabase_service

load_dotenv()
logger = logging.getLogger(__name__)

mock_analyses: list[dict] = []


class InMemoryDementiaBackend:
    @staticmethod
    def create_analysis_record(user_id: str, answer_id: str) -> dict:
        record = {
            "analysis_id": f"analysis_{uuid.uuid4().hex[:8]}",
            "answer_id": answer_id,
            "user_id": user_id,
            "status": "pending",
            "transcript": None,
            "risk_level": None,
            "risk_score": None,
            "analysis_summary": None,
            "indicators": None,
            "created_at": datetime.now(),
            "completed_at": None,
        }
        mock_analyses.append(record)
        return record

    @staticmethod
    def get_analysis(analysis_id: str) -> dict | None:
        for rec in mock_analyses:
            if rec["analysis_id"] == analysis_id:
                return rec
        return None

    @staticmethod
    def get_user_analyses(user_id: str) -> list[dict]:
        filtered = [a for a in mock_analyses if a["user_id"] == user_id]
        return sorted(filtered, key=lambda x: x["created_at"], reverse=True)

    @staticmethod
    def update_analysis_record(analysis_id: str, **changes) -> dict:
        record = InMemoryDementiaBackend.get_analysis(analysis_id)
        if not record:
            raise HTTPException(status_code=404, detail="Analysis not found")
        record.update(changes)
        return record


class SupabaseDementiaBackend:
    @property
    def table(self) -> str:
        return os.getenv("SUPABASE_DEMENTIA_ANALYSES_TABLE", "dementia_analyses")

    @staticmethod
    def is_configured() -> bool:
        return supabase_service.is_configured()

    def create_analysis_record(self, user_id: str, answer_id: str) -> dict:
        record = {
            "analysis_id": f"analysis_{uuid.uuid4().hex[:8]}",
            "answer_id": answer_id,
            "user_id": user_id,
            "status": "pending",
            "transcript": None,
            "risk_level": None,
            "risk_score": None,
            "analysis_summary": None,
            "indicators": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        }
        return supabase_service.insert(self.table, record)[0]

    def get_analysis(self, analysis_id: str) -> dict | None:
        rows = supabase_service.select(
            self.table,
            filters=[("analysis_id", f"eq.{analysis_id}")],
            limit=1,
        )
        return rows[0] if rows else None

    def get_user_analyses(self, user_id: str) -> list[dict]:
        return supabase_service.select(
            self.table,
            filters=[("user_id", f"eq.{user_id}")],
            order="created_at.desc",
        )

    def update_analysis_record(self, analysis_id: str, **changes) -> dict:
        rows = supabase_service.update(
            self.table,
            filters=[("analysis_id", f"eq.{analysis_id}")],
            payload=changes,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Analysis not found")
        return rows[0]


class DementiaService:
    def __init__(self) -> None:
        self._transcribe_client = None
        self._memory_backend = InMemoryDementiaBackend()
        self._supabase_backend = SupabaseDementiaBackend()
        self._backend_override = None

    def set_backend(self, backend) -> None:
        self._backend_override = backend

    def reset_backend(self) -> None:
        self._backend_override = None

    def _backend(self):
        if self._backend_override is not None:
            return self._backend_override
        if self._supabase_backend.is_configured():
            return self._supabase_backend
        if os.getenv("ALLOW_IN_MEMORY_FALLBACK", "").lower() == "true":
            return self._memory_backend
        raise HTTPException(
            status_code=500,
            detail="Supabase is not configured for dementia analysis persistence.",
        )

    def _get_transcribe_client(self):
        if self._transcribe_client is None:
            self._transcribe_client = boto3.client(
                "transcribe",
                region_name=os.getenv("DATA_AWS_REGION", "ap-northeast-2"),
            )
        return self._transcribe_client

    def create_analysis_record(self, user_id: str, answer_id: str) -> dict:
        return self._backend().create_analysis_record(user_id, answer_id)

    def get_analysis(self, analysis_id: str) -> dict | None:
        return self._backend().get_analysis(analysis_id)

    def get_user_analyses(self, user_id: str) -> list[dict]:
        return self._backend().get_user_analyses(user_id)

    def update_analysis_record(self, analysis_id: str, **changes) -> dict:
        return self._backend().update_analysis_record(analysis_id, **changes)

    def _resolve_s3_uri(self, voice_file_key: str) -> tuple[str, str]:
        if voice_file_key.startswith("s3://"):
            without_scheme = voice_file_key[5:]
            bucket, _, key = without_scheme.partition("/")
            return bucket, key

        if voice_file_key.startswith("https://"):
            without_scheme = voice_file_key[8:]
            host, _, key = without_scheme.partition("/")
            bucket = host.split(".")[0]
            return bucket, key

        raise HTTPException(status_code=400, detail=f"Invalid voice_file_key format: {voice_file_key}")

    def _start_transcription(self, analysis_id: str, voice_file_key: str) -> str:
        bucket, key = self._resolve_s3_uri(voice_file_key)
        media_uri = f"s3://{bucket}/{key}"
        extension = key.rsplit(".", 1)[-1].lower() if "." in key else "mp4"
        media_format_map = {
            "mp3": "mp3",
            "wav": "wav",
            "m4a": "mp4",
            "mp4": "mp4",
        }
        media_format = media_format_map.get(extension, "mp4")
        job_name = f"dementia-{analysis_id}-{uuid.uuid4().hex[:6]}"

        try:
            self._get_transcribe_client().start_transcription_job(
                TranscriptionJobName=job_name,
                Media={"MediaFileUri": media_uri},
                MediaFormat=media_format,
                LanguageCode="ko-KR",
            )
        except (ClientError, BotoCoreError) as exc:
            logger.exception("Transcribe 시작 실패 - job=%s", job_name)
            self.update_analysis_record(analysis_id, status="failed")
            raise HTTPException(status_code=502, detail=f"Transcribe start failed: {exc}") from exc
        return job_name

    def _wait_for_transcription(self, analysis_id: str, job_name: str) -> str:
        client = self._get_transcribe_client()
        max_wait = 300
        poll_interval = 5
        elapsed = 0

        while elapsed < max_wait:
            try:
                resp = client.get_transcription_job(TranscriptionJobName=job_name)
            except (ClientError, BotoCoreError) as exc:
                logger.exception("Transcribe 상태 조회 실패 - job=%s", job_name)
                self.update_analysis_record(analysis_id, status="failed")
                raise HTTPException(status_code=502, detail=f"Transcribe polling failed: {exc}") from exc

            status = resp["TranscriptionJob"]["TranscriptionJobStatus"]
            if status == "COMPLETED":
                transcript_uri = resp["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
                return self._fetch_transcript_text(transcript_uri)

            if status == "FAILED":
                reason = resp["TranscriptionJob"].get("FailureReason", "unknown")
                self.update_analysis_record(analysis_id, status="failed")
                raise HTTPException(status_code=502, detail=f"Transcribe failed: {reason}")

            time.sleep(poll_interval)
            elapsed += poll_interval

        self.update_analysis_record(analysis_id, status="failed")
        raise HTTPException(status_code=504, detail="Transcribe timeout")

    def _fetch_transcript_text(self, transcript_uri: str) -> str:
        try:
            with urllib.request.urlopen(transcript_uri) as response:
                data = json.loads(response.read().decode("utf-8"))
            transcripts = data.get("results", {}).get("transcripts", [])
            if transcripts:
                return transcripts[0].get("transcript", "")
            return ""
        except Exception as exc:
            logger.exception("Transcribe 결과 다운로드 실패 - uri=%s", transcript_uri)
            raise HTTPException(status_code=502, detail=f"Failed to fetch transcript: {exc}") from exc

    def _analyze_with_llm(self, analysis_id: str, transcript: str) -> dict:
        api_gateway_url = os.getenv("LLM_API_GATEWAY_URL")
        if not api_gateway_url:
            self.update_analysis_record(analysis_id, status="failed")
            raise HTTPException(status_code=500, detail="LLM_API_GATEWAY_URL is not configured")

        try:
            payload = json.dumps({"transcript": transcript}).encode("utf-8")
            req = urllib.request.Request(
                api_gateway_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                resp_body = json.loads(resp.read().decode("utf-8"))

            if isinstance(resp_body, dict) and "body" in resp_body:
                result = json.loads(resp_body["body"]) if isinstance(resp_body["body"], str) else resp_body["body"]
            else:
                result = resp_body

            if "error" in result:
                self.update_analysis_record(analysis_id, status="failed")
                raise HTTPException(status_code=502, detail=f"LLM analysis failed: {result['error']}")
            return result
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            self.update_analysis_record(analysis_id, status="failed")
            raise HTTPException(status_code=502, detail=f"LLM API call failed (HTTP {exc.code}): {error_body}") from exc
        except urllib.error.URLError as exc:
            self.update_analysis_record(analysis_id, status="failed")
            raise HTTPException(status_code=502, detail=f"LLM API connection failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            self.update_analysis_record(analysis_id, status="failed")
            raise HTTPException(status_code=502, detail=f"LLM response parse failed: {exc}") from exc

    async def run_analysis_pipeline(self, analysis_record: dict, voice_file_key: str) -> None:
        import asyncio

        analysis_id = analysis_record["analysis_id"]
        try:
            self.update_analysis_record(analysis_id, status="transcribing")
            job_name = await asyncio.to_thread(self._start_transcription, analysis_id, voice_file_key)
            transcript = await asyncio.to_thread(self._wait_for_transcription, analysis_id, job_name)
            self.update_analysis_record(
                analysis_id,
                status="transcribed",
                transcript=transcript,
            )

            if not transcript.strip():
                self.update_analysis_record(
                    analysis_id,
                    status="completed",
                    risk_level="low",
                    risk_score=0.0,
                    analysis_summary="발화 내용이 비어 있어 분석을 수행할 수 없습니다.",
                    indicators=[],
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
                return

            self.update_analysis_record(analysis_id, status="analyzing")
            llm_result = await asyncio.to_thread(self._analyze_with_llm, analysis_id, transcript)
            completed_record = self.update_analysis_record(
                analysis_id,
                status="completed",
                risk_level=llm_result.get("risk_level", "low"),
                risk_score=llm_result.get("risk_score", 0.0),
                analysis_summary=llm_result.get("analysis_summary", ""),
                indicators=llm_result.get("indicators", []),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )

            risk_label = {"low": "낮음", "medium": "보통", "high": "높음"}.get(
                completed_record["risk_level"], completed_record["risk_level"]
            )
            notification_service.send(
                user_id=completed_record["user_id"],
                title="건강 분석이 완료됐어요",
                body=f"위험도: {risk_label}",
                data={
                    "analysis_id": completed_record["analysis_id"],
                    "risk_level": completed_record["risk_level"],
                    "type": "dementia_analysis_done",
                },
            )
        except HTTPException:
            logger.warning("파이프라인 중단 - analysis_id=%s", analysis_id)
        except Exception:
            self.update_analysis_record(analysis_id, status="failed")
            logger.exception("파이프라인 예외 - analysis_id=%s", analysis_id)


dementia_service = DementiaService()
