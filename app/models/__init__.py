from app.database import Base  # Import your Base first
from .user import User
from .subject import Subject
from .module import Module
from .lesson import Lesson
from .knowledge_node import KnowledgeNode
from .knowledge_edge import KnowledgeEdge
from .question import Question
from .study_session import StudySession
from .practice_result import PracticeResult
from .generated_mindmap import GeneratedMindmap

# This is crucial for Alembic to "see" everything
target_metadata = Base.metadata