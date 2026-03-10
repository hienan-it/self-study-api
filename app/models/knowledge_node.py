from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.database import Base

class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"
    id = Column(Integer, primary_key=True, index=True)
    module_id = Column(Integer, ForeignKey("modules.id"))
    subject_id = Column(Integer, ForeignKey("subjects.id"))
    lesson_id = Column(Integer, ForeignKey("lessons.id"))
    grade = Column(Integer)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    node_type = Column(String(50))
    difficulty_level = Column(String(50))
    importance_weight = Column(Integer)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())