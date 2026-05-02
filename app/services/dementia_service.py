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
import urllib.request
import uuid
from datetime import datetime

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()
logger = logging.getLogger(__name__)

# ── in-memory 저장소 (향후 DynamoDB 연동) ──
mock_analyses: list[dict] = []


class DementiaService:
    """S3 음성 → Transcribe STT → Lambda(OpenAI) 치매 분석 파이프라인"""

    def __init__(self) -> None:
        self._transcribe_client = None

    # ────────────────────────── AWS 클라이언트 lazy init ──

    def _get_transcribe_client(self):
        if self._transcribe_client is None:
            self._transcribe_client = boto3.client(
                "transcribe",
                region_name=os.getenv("AWS_REGION", "ap-northeast-2"),
            )
        return self._transcribe_client

    # ────────────────────────── 분석 레코드 CRUD ──

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

    # ────────────────────────── 1단계: S3 URI → Transcribe ──

    def _resolve_s3_uri(self, voice_file_key: str) -> tuple[str, str]:
        """
        voice_file_key 형식 예시:
          - s3://cloud-compute-team-e/voices/parent_001/abc123.m4a
          - https://cloud-compute-team-e.s3.ap-northeast-2.amazonaws.com/voices/...
        반환: (bucket, key)
        """
        if voice_file_key.startswith("s3://"):
            without_scheme = voice_file_key[5:]
            bucket, _, key = without_scheme.partition("/")
            return bucket, key

        if voice_file_key.startswith("https://"):
            # https://bucket.s3.region.amazonaws.com/key
            without_scheme = voice_file_key[8:]
            host, _, key = without_scheme.partition("/")
            bucket = host.split(".")[0]
            return bucket, key

        raise HTTPException(status_code=400, detail=f"Invalid voice_file_key format: {voice_file_key}")

    def _start_transcription(self, analysis_record: dict, voice_file_key: str) -> str:
        """Transcribe 작업을 시작하고 job name을 반환한다."""
        bucket, key = self._resolve_s3_uri(voice_file_key)
        media_uri = f"s3://{bucket}/{key}"

        # 확장자로 미디어 포맷 결정
        extension = key.rsplit(".", 1)[-1].lower() if "." in key else "mp4"
        media_format_map = {
            "mp3": "mp3",
            "wav": "wav",
            "m4a": "mp4",
            "mp4": "mp4",
        }
        media_format = media_format_map.get(extension, "mp4")

        job_name = f"dementia-{analysis_record['analysis_id']}-{uuid.uuid4().hex[:6]}"

        logger.info(
            "Transcribe 작업 시작 - job=%s, media_uri=%s, format=%s",
            job_name, media_uri, media_format,
        )

        try:
            self._get_transcribe_client().start_transcription_job(
                TranscriptionJobName=job_name,
                Media={"MediaFileUri": media_uri},
                MediaFormat=media_format,
                LanguageCode="ko-KR",
            )
        except (ClientError, BotoCoreError) as exc:
            logger.exception("Transcribe 시작 실패 - job=%s", job_name)
            analysis_record["status"] = "failed"
            raise HTTPException(status_code=502, detail=f"Transcribe start failed: {exc}") from exc

        return job_name

    def _wait_for_transcription(self, job_name: str, analysis_record: dict) -> str:
        """Transcribe 작업 완료를 폴링하고, 결과 텍스트를 반환한다."""
        client = self._get_transcribe_client()
        max_wait = 300  # 최대 5분
        poll_interval = 5

        elapsed = 0
        while elapsed < max_wait:
            try:
                resp = client.get_transcription_job(TranscriptionJobName=job_name)
            except (ClientError, BotoCoreError) as exc:
                logger.exception("Transcribe 상태 조회 실패 - job=%s", job_name)
                analysis_record["status"] = "failed"
                raise HTTPException(status_code=502, detail=f"Transcribe polling failed: {exc}") from exc

            status = resp["TranscriptionJob"]["TranscriptionJobStatus"]
            logger.info("Transcribe 상태 - job=%s, status=%s", job_name, status)

            if status == "COMPLETED":
                transcript_uri = resp["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
                return self._fetch_transcript_text(transcript_uri)

            if status == "FAILED":
                reason = resp["TranscriptionJob"].get("FailureReason", "unknown")
                logger.error("Transcribe 실패 - job=%s, reason=%s", job_name, reason)
                analysis_record["status"] = "failed"
                raise HTTPException(status_code=502, detail=f"Transcribe failed: {reason}")

            time.sleep(poll_interval)
            elapsed += poll_interval

        analysis_record["status"] = "failed"
        raise HTTPException(status_code=504, detail="Transcribe timeout")

    def _fetch_transcript_text(self, transcript_uri: str) -> str:
        """Transcribe 결과 JSON에서 텍스트를 추출한다."""
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

    # ────────────────────────── 2단계: Lambda(OpenAI) 치매 분석 ──

    def _analyze_with_llm(self, transcript: str, analysis_record: dict) -> dict:
        """
        API Gateway + Lambda를 통해 OpenAI GPT로 발화 텍스트의 치매 위험을 분석한다.
        Lambda 내부에서 OpenAI API를 호출하므로, 백엔드 서버에는 OpenAI 키가 필요 없다.
        """
        api_gateway_url = os.getenv("LLM_API_GATEWAY_URL")
        if not api_gateway_url:
            logger.error("LLM_API_GATEWAY_URL 환경변수가 설정되지 않음")
            analysis_record["status"] = "failed"
            raise HTTPException(
                status_code=500,
                detail="LLM_API_GATEWAY_URL is not configured",
            )

        logger.info(
            "LLM 분석 요청 - url=%s, transcript_length=%d",
            api_gateway_url,
            len(transcript),
        )

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

            # API Gateway + Lambda 응답 구조 처리
            # Lambda가 API Gateway proxy 형식이면 body가 문자열일 수 있음
            if isinstance(resp_body, dict) and "body" in resp_body:
                result = json.loads(resp_body["body"]) if isinstance(resp_body["body"], str) else resp_body["body"]
            else:
                result = resp_body

            # 에러 응답 확인
            if "error" in result:
                logger.error("LLM 분석 에러 응답 - error=%s", result["error"])
                analysis_record["status"] = "failed"
                raise HTTPException(status_code=502, detail=f"LLM analysis failed: {result['error']}")

            logger.info(
                "LLM 분석 완료 - risk_level=%s, risk_score=%s",
                result.get("risk_level"),
                result.get("risk_score"),
            )
            return result

        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace") if exc.readable() else str(exc)
            logger.exception("API Gateway 호출 HTTP 에러 - status=%s", exc.code)
            analysis_record["status"] = "failed"
            raise HTTPException(status_code=502, detail=f"LLM API call failed (HTTP {exc.code}): {error_body}") from exc
        except urllib.error.URLError as exc:
            logger.exception("API Gateway 연결 실패")
            analysis_record["status"] = "failed"
            raise HTTPException(status_code=502, detail=f"LLM API connection failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            logger.exception("LLM 응답 JSON 파싱 실패")
            analysis_record["status"] = "failed"
            raise HTTPException(status_code=502, detail=f"LLM response parse failed: {exc}") from exc

    # ────────────────────────── 전체 파이프라인 (백그라운드) ──

    async def run_analysis_pipeline(self, analysis_record: dict, voice_file_key: str) -> None:
        """
        백그라운드에서 실행되는 전체 분석 파이프라인:
        1. S3 음성 → Transcribe STT
        2. STT 결과 → Lambda(OpenAI) 치매 위험 분석
        """
        import asyncio

        try:
            # 1단계: Transcribe
            analysis_record["status"] = "transcribing"
            logger.info("파이프라인 시작 - analysis_id=%s", analysis_record["analysis_id"])

            job_name = await asyncio.to_thread(
                self._start_transcription, analysis_record, voice_file_key
            )
            transcript = await asyncio.to_thread(
                self._wait_for_transcription, job_name, analysis_record
            )

            analysis_record["status"] = "transcribed"
            analysis_record["transcript"] = transcript
            logger.info(
                "STT 완료 - analysis_id=%s, transcript_length=%d",
                analysis_record["analysis_id"],
                len(transcript),
            )

            if not transcript.strip():
                analysis_record["status"] = "completed"
                analysis_record["risk_level"] = "low"
                analysis_record["risk_score"] = 0.0
                analysis_record["analysis_summary"] = "발화 내용이 비어 있어 분석을 수행할 수 없습니다."
                analysis_record["indicators"] = []
                analysis_record["completed_at"] = datetime.now()
                logger.info("빈 발화 - 분석 건너뜀 - analysis_id=%s", analysis_record["analysis_id"])
                return

            # 2단계: Lambda(OpenAI) 분석
            analysis_record["status"] = "analyzing"
            llm_result = await asyncio.to_thread(
                self._analyze_with_llm, transcript, analysis_record
            )

            analysis_record["status"] = "completed"
            analysis_record["risk_level"] = llm_result.get("risk_level", "low")
            analysis_record["risk_score"] = llm_result.get("risk_score", 0.0)
            analysis_record["analysis_summary"] = llm_result.get("analysis_summary", "")
            analysis_record["indicators"] = llm_result.get("indicators", [])
            analysis_record["completed_at"] = datetime.now()

            logger.info(
                "치매 분석 완료 - analysis_id=%s, risk_level=%s, risk_score=%s",
                analysis_record["analysis_id"],
                analysis_record["risk_level"],
                analysis_record["risk_score"],
            )

        except HTTPException:
            # 이미 status=failed 처리됨
            logger.warning("파이프라인 중단 - analysis_id=%s", analysis_record["analysis_id"])
        except Exception:
            analysis_record["status"] = "failed"
            logger.exception("파이프라인 예외 - analysis_id=%s", analysis_record["analysis_id"])


dementia_service = DementiaService()
