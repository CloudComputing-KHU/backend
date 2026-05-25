from pydantic import BaseModel
from typing import List, Literal, Optional

QuestionType = Literal["health", "meal", "mood"]

class Question(BaseModel):
    question_id: str
    type: QuestionType
    text: str
    options: List[str]
    allow_voice: bool


class DailyQuestionProgress(BaseModel):
    user_id: str
    health_answered: bool
    meal_answered: bool
    mood_answered: bool
    completed_count: int
    next_type: Optional[QuestionType] = None
    all_answered: bool
