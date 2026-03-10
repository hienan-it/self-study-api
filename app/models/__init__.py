"""
Import all models here so Alembic can detect them
"""

# User models
from app.models.user import User, UserRole

# Subject and Module models
from app.models.subject import Subject
from app.models.module import Module
from app.models.lesson import Lesson, lesson_knowledge

# Knowledge Graph models
from app.models.knowledge import (
    KnowledgeNode,
    KnowledgeEdge,
    NodeType,
    DifficultyLevel,
    RelationType
)

# Question models
from app.models.question import (
    Question,
    QuestionType,
    QuestionDifficulty
)

# Session and Result models
from app.models.session import (
    StudySession,
    PracticeResult,
    GeneratedMindmap
)

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