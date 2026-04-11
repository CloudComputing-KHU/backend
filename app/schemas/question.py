from pydantic import BaseModel
from typing import List, Literal

QuestionType = Literal["health", "meal", "mood"]

class Question(BaseModel):
    question_id: str
    type: QuestionType
    text: str
    options: List[str]
    allow_voice: bool
