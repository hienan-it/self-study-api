"""
Import all models here so Alembic can detect them
"""
from app.db.models.knowledge import KnowledgeNode, KnowledgeEdge, NodeType, RelationType, DifficultyLevel
from app.db.models.session import StudySession, PracticeResult, GeneratedMindmap
from app.db.models.subject import Subject
# User models
from app.db.models.user import User, UserRole

# Subject and Module models
from app.db.models.module import Module
from app.db.models.lesson import Lesson, lesson_knowledge

# Knowledge Graph models

# Question models
from app.db.models.question import (
    Question,
    QuestionType,
    QuestionDifficulty
)

# Session and Result models

__all__ = [
    # User
    "User",
    "UserRole",

    # Subject & Module
    "Subject",
    "Module",
    "Lesson",
    "lesson_knowledge",

    # Knowledge Graph
    "KnowledgeNode",
    "KnowledgeEdge",
    "NodeType",
    "DifficultyLevel",
    "RelationType",

    # Questions
    "Question",
    "QuestionType",
    "QuestionDifficulty",

    # Sessions
    "StudySession",
    "PracticeResult",
    "GeneratedMindmap",
]