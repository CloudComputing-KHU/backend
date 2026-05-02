"""
Lambda function: 치매 위험 분석
- API Gateway로부터 transcript(발화 텍스트)를 받아 OpenAI GPT로 분석
- 결과를 JSON으로 반환
"""

import json
import os

import openai


def lambda_handler(event, context):
    """API Gateway → Lambda 진입점"""
    try:
        # API Gateway에서 body 파싱
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event.get("body") or event

        transcript = body.get("transcript", "")

        if not transcript.strip():
            return _response(200, {
                "risk_level": "low",
                "risk_score": 0.0,
                "analysis_summary": "발화 내용이 비어 있어 분석을 수행할 수 없습니다.",
                "indicators": [],
            })

        # OpenAI API 호출
        result = analyze_dementia_risk(transcript)

        return _response(200, result)

    except json.JSONDecodeError as exc:
        return _response(400, {"error": f"Invalid JSON: {exc}"})
    except openai.AuthenticationError as exc:
        return _response(500, {"error": f"OpenAI authentication failed: {exc}"})
    except openai.RateLimitError as exc:
        return _response(429, {"error": f"OpenAI rate limit: {exc}"})
    except Exception as exc:
        return _response(500, {"error": f"Internal error: {exc}"})


def analyze_dementia_risk(transcript: str) -> dict:
    """OpenAI GPT를 사용하여 발화 텍스트에서 치매 위험 지표를 분석한다."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    client = openai.OpenAI(api_key=api_key)

    prompt = f"""당신은 노인 발화를 분석하여 치매 위험 지표를 감지하는 전문 AI 분석가입니다.

아래는 노인의 음성을 텍스트로 변환한 발화 내용입니다. 이 발화를 분석하여 치매 위험 요소를 평가해 주세요.

발화 내용:
\"\"\"{transcript}\"\"\"

다음 기준으로 분석해 주세요:
1. 단어 찾기 어려움 (word-finding difficulty): 적절한 단어를 떠올리지 못하고 "그거", "저거" 등 대명사를 과다 사용
2. 반복 발화 (repetition): 같은 말이나 구절을 반복
3. 문장 구조 단순화: 복잡한 문장 구성 능력 저하
4. 시간/장소 혼동: 시간이나 장소에 대한 혼동
5. 주제 이탈 (topic drift): 대화 주제에서 벗어남
6. 기억 관련 표현: "기억이 안 나요", "잊어버렸어요" 등의 표현 빈도
7. 발화 유창성: 머뭇거림, 중단, 비정상적 쉼이 많은지

결과를 반드시 아래 JSON 형식으로만 응답해 주세요. 다른 텍스트 없이 JSON만 출력하세요:
{{
    "risk_level": "low | medium | high",
    "risk_score": 0.0~1.0 사이의 소수 (0은 위험 없음, 1은 매우 높은 위험),
    "analysis_summary": "분석 요약 (한국어, 2~3문장)",
    "indicators": ["감지된 지표 1", "감지된 지표 2"]
}}"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": prompt},
        ],
        max_tokens=1024,
        temperature=0.3,
    )

    assistant_text = response.choices[0].message.content

    # JSON 파싱 (코드 블록 제거)
    cleaned = assistant_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    result = json.loads(cleaned)
    return result


def _response(status_code: int, body: dict) -> dict:
    """API Gateway용 응답 포맷"""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, ensure_ascii=False),
    }
