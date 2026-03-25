from sqlalchemy import Column, Integer, ForeignKey, Float, DateTime
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.models.base_model import BaseModel


class StudySession(BaseModel):
    """Study Session - Track user learning sessions"""
    __tablename__ = "study_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    grade = Column(Integer, nullable=False)
    selected_lessons = Column(JSON, nullable=False)  # List of lesson IDs
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="study_sessions")
    practice_results = relationship("PracticeResult", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<StudySession(id={self.id}, user_id={self.user_id}, grade={self.grade})>"


class PracticeResult(BaseModel):
    """Practice Result - Results from practice/quiz"""
    __tablename__ = "practice_results"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("study_sessions.id", ondelete="CASCADE"), nullable=False)
    total_questions = Column(Integer, nullable=False)
    correct_answers = Column(Integer, nullable=False)
    score = Column(Float, nullable=False)  # Percentage score
    time_spent = Column(Integer, nullable=False)  # Seconds
    answers = Column(JSON, nullable=True)  # Detailed answer data

    # Relationships
    session = relationship("StudySession", back_populates="practice_results")

    def __repr__(self):
        return f"<PracticeResult(id={self.id}, score={self.score}%)>"


class GeneratedMindmap(BaseModel):
    """Generated Mindmap - AI-generated mindmaps for users"""
    __tablename__ = "generated_mindmaps"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    root_node_id = Column(Integer, ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False)
    structure = Column(JSON, nullable=False)  # Tree structure of mindmap

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="mindmaps")
    root_node = relationship("KnowledgeNode")

    def __repr__(self):
        return f"<GeneratedMindmap(id={self.id}, user_id={self.user_id})>"