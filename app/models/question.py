from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.sql import func
from app.database import Base

class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, index=True)
    knowledge_node_id = Column(Integer, ForeignKey("knowledge_nodes.id"))
    question_type = Column(String(50))
    difficulty = Column(Integer)
    content = Column(Text)
    options = Column(JSON)
    correct_answer = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())