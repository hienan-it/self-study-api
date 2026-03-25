from sqlalchemy import Column, Integer, String, ForeignKey, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import relationship
import enum
from app.db.models.base_model import BaseModel
from app.utils.enum_as_string import EnumAsString


class QuestionType(str, enum.Enum):
    """Types of questions"""
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"
    ESSAY = "essay"
    FILL_BLANK = "fill_blank"


class QuestionDifficulty(str, enum.Enum):
    """Question difficulty levels"""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Question(BaseModel):
    """Question model - Assessment questions for knowledge nodes"""
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    knowledge_node_id = Column(Integer, ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False)
    question_type = Column(EnumAsString(QuestionType), nullable=False)
    difficulty = Column(EnumAsString(QuestionDifficulty), default=QuestionDifficulty.MEDIUM, nullable=False)
    content = Column(Text, nullable=False)  # Question text
    options = Column(JSON, nullable=True)  # For multiple choice: {"A": "...", "B": "...", ...}
    correct_answer = Column(String(500), nullable=False)  # Answer key
    explanation = Column(Text, nullable=True)  # Explanation of answer

    # Relationships
    knowledge_node = relationship("KnowledgeNode", back_populates="questions")

    def __repr__(self):
        return f"<Question(id={self.id}, type={self.question_type}, difficulty={self.difficulty})>"