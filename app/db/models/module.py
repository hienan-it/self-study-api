from sqlalchemy import Column, Integer, String, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.db.models.base_model import BaseModel


class Module(BaseModel):
    __tablename__ = "modules"
    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    grade = Column(Integer, nullable=False)  # e.g., 1-12
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    display_order = Column(Integer, default=0)

    # Relationships
    subject = relationship("Subject", back_populates="modules")
    lessons = relationship("Lesson", back_populates="module", cascade="all, delete-orphan")
    knowledge_nodes = relationship("KnowledgeNode", back_populates="module")

    def __repr__(self):
        return f"<Module(id={self.id}, name={self.name}, grade={self.grade})>"