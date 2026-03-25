from datetime import datetime
from typing import List, Optional

from pydantic import Field

from app.schemas.base import APIModel
from app.schemas.mixins.auditable import AuditableSchema
from app.db.models import DifficultyLevel


class StudySessionCreate(APIModel):
    grade: int
    selected_lessons: List[int]


class StudySessionResponse(APIModel, AuditableSchema):
    id: int
    user_id: int
    grade: int
    selected_lessons: List[int]
    completed_at: Optional[datetime] = None


class AnswerItem(APIModel):
    question_id: int
    selected_answer: str
    is_correct: bool
    time_spent_seconds: int = 0


class PracticeResultCreate(APIModel):
    session_id: int
    total_questions: int
    correct_answers: int
    score: float = Field(ge=0.0, le=100.0)
    time_spent: int
    answers: Optional[List[AnswerItem]] = None


class PracticeResultResponse(APIModel, AuditableSchema):
    id: int
    session_id: int
    total_questions: int
    correct_answers: int
    score: float
    time_spent: int
    answers: Optional[List[AnswerItem]] = None


class MasteryReport(APIModel):
    session_id: int
    total_questions: int
    correct_answers: int
    score: float
    mastery_level: str
    weak_node_ids: List[int]
    strong_node_ids: List[int]
    recommendations: List[str]


class QuestionSelectionRequest(APIModel):
    lesson_ids: List[int]
    num_questions: int = Field(default=10, ge=1, le=50)
    difficulty: Optional[DifficultyLevel] = None


class QuestionItem(APIModel):
    question_id: int
    knowledge_node_id: int
    knowledge_node_title: str
    question_type: str
    difficulty: str
    content: str
    options: Optional[dict] = None