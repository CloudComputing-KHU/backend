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

from app.services.notification_service import notification_service

load_dotenv()
logger = logging.getLogger(__name__)

# ── in-memory 저장소 (향후 DynamoDB 연동) ──
mock_analyses: list[dict] = []


class DementiaService:
    """S3 음성 ➔ OpenAI Whisper STT ➔ Lambda(OpenAI) 치매 분석 파이프라인"""

    def __init__(self) -> None:
        self._s3_client = None
        self._openai_client = None

    # ────────────────────────── AWS 및 OpenAI 클라이언트 lazy init ──

    def _get_s3_client(self):
        if self._s3_client is None:
            self._s3_client = boto3.client(
                "s3",
                region_name=os.getenv("DATA_AWS_REGION", "ap-northeast-2"),
            )
        return self._s3_client

    def _get_openai_client(self):
        if self._openai_client is None:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.error("OPENAI_API_KEY 환경변수가 설정되지 않음")
                raise ValueError("OPENAI_API_KEY environment variable is not set")
            from openai import OpenAI
            self._openai_client = OpenAI(api_key=api_key)
        return self._openai_client

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

    # ────────────────────────── S3 URI 파싱 ──

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
            without_scheme = voice_file_key[8:]
            host, _, key = without_scheme.partition("/")
            bucket = host.split(".")[0]
            return bucket, key

        raise HTTPException(status_code=400, detail=f"Invalid voice_file_key format: {voice_file_key}")

    # ────────────────────────── OpenAI Whisper STT 변환 ──

    def _speech_to_text_whisper(self, voice_file_key: str, analysis_record: dict) -> str:
        """S3에서 음성 파일을 다운로드하여 OpenAI Whisper API로 텍스트 변환한다."""
        import tempfile
        
        bucket, key = self._resolve_s3_uri(voice_file_key)
        
        try:
            # 1. S3에서 파일 다운로드
            s3 = self._get_s3_client()
            logger.info("S3 음성 파일 다운로드 중 - bucket=%s, key=%s", bucket, key)
            s3_response = s3.get_object(Bucket=bucket, Key=key)
            audio_bytes = s3_response["Body"].read()
            
            # 2. 오디오 확장자에 맞게 임시 파일 작성
            extension = key.rsplit(".", 1)[-1].lower() if "." in key else "m4a"
            
            with tempfile.NamedTemporaryFile(suffix=f".{extension}", delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_filepath = temp_file.name
                
            logger.info("임시 오디오 파일 저장 완료 - path=%s", temp_filepath)
        except Exception as exc:
            logger.exception("S3 다운로드 혹은 임시 파일 생성 실패")
            analysis_record["status"] = "failed"
            raise HTTPException(status_code=502, detail=f"Audio download failed: {exc}") from exc

        try:
            # 3. OpenAI Whisper API 호출
            logger.info("OpenAI Whisper API 호출 중 - filepath=%s", temp_filepath)
            client = self._get_openai_client()
            
            with open(temp_filepath, "rb") as audio_file:
                transcript_obj = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="ko"
                )
                
            transcript_text = transcript_obj.text
            logger.info("Whisper STT 완료 - transcript_length=%d", len(transcript_text))
            return transcript_text
            
        except Exception as exc:
            logger.exception("OpenAI Whisper API 호출 실패")
            analysis_record["status"] = "failed"
            raise HTTPException(status_code=502, detail=f"Whisper STT failed: {exc}") from exc
            
        finally:
            # 4. 임시 파일 정리
            if os.path.exists(temp_filepath):
                try:
                    os.remove(temp_filepath)
                except Exception:
                    pass

    # ────────────────────────── Lambda(OpenAI) 치매 분석 ──

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
        1. S3 음성 ➔ OpenAI Whisper STT
        2. STT 결과 ➔ Lambda(OpenAI) 치매 위험 분석
        """
        import asyncio

        try:
            # 1단계: Whisper STT 변환
            analysis_record["status"] = "transcribing"
            logger.info("Whisper 파이프라인 시작 - analysis_id=%s", analysis_record["analysis_id"])

            transcript = await asyncio.to_thread(
                self._speech_to_text_whisper, voice_file_key, analysis_record
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
            risk_label = {"low": "낮음", "medium": "보통", "high": "높음"}.get(
                analysis_record["risk_level"], analysis_record["risk_level"]
            )
            notification_service.send(
                user_id=analysis_record["user_id"],
                title="건강 분석이 완료됐어요",
                body=f"위험도: {risk_label}",
                data={
                    "analysis_id": analysis_record["analysis_id"],
                    "risk_level": analysis_record["risk_level"],
                    "type": "dementia_analysis_done",
                },
            )

        except HTTPException:
            # 이미 status=failed 처리됨
            logger.warning("파이프라인 중단 - analysis_id=%s", analysis_record["analysis_id"])
        except Exception:
            analysis_record["status"] = "failed"
            logger.exception("파이프라인 예외 - analysis_id=%s", analysis_record["analysis_id"])


dementia_service = DementiaService()
