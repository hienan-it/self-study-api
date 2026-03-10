from sqlalchemy import Column, Integer, JSON, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base

class StudySession(Base):
    __tablename__ = "study_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    grade = Column(Integer)
    selected_lessons = Column(JSON)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())