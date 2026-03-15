from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models import DifficultyLevel


class StudySessionCreate(BaseModel):
    grade: int
    selected_lessons: List[int]  # List of lesson IDs


class StudySessionResponse(BaseModel):
    id: int
    user_id: int
    grade: int
    selected_lessons: List[int]
    created_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class AnswerItem(BaseModel):
    question_id: int
    selected_answer: str
    is_correct: bool
    time_spent_seconds: int = 0


class PracticeResultCreate(BaseModel):
    session_id: int
    total_questions: int
    correct_answers: int
    score: float = Field(ge=0.0, le=100.0)
    time_spent: int  # seconds
    answers: Optional[List[AnswerItem]] = None


class PracticeResultResponse(BaseModel):
    id: int
    session_id: int
    total_questions: int
    correct_answers: int
    score: float
    time_spent: int
    answers: Optional[list]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class MasteryReport(BaseModel):
    session_id: int
    total_questions: int
    correct_answers: int
    score: float
    mastery_level: str  # "beginner" | "developing" | "proficient" | "mastered"
    weak_node_ids: List[int]  # Nodes where user struggled
    strong_node_ids: List[int]  # Nodes where user excelled
    recommendations: List[str]  # Human-readable suggestions


class QuestionSelectionRequest(BaseModel):
    lesson_ids: List[int]
    num_questions: int = Field(default=10, ge=1, le=50)
    difficulty: Optional[DifficultyLevel] = None


class QuestionItem(BaseModel):
    question_id: int
    knowledge_node_id: int
    knowledge_node_title: str
    question_type: str
    difficulty: str
    content: str
    options: Optional[dict]