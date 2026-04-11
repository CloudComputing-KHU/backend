import asyncio

class AIService:
    @staticmethod
    async def mock_ai_analysis_task(answer_record: dict):
        # TODO: STT 연동
        await asyncio.sleep(3)
        
        answer_record["voice_status"] = "analyzed"
        answer_record["answer"] = "[음성 인식 대기 중]"

ai_service = AIService()
