from sqlalchemy import Column, Integer, String                , Text
from sqlalchemy.orm import relationship
from app.db.models.base_model import BaseModel


class Subject(BaseModel):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Relationships
    modules = relationship("Module", back_populates="subject", cascade="all, delete-orphan")
    knowledge_nodes = relationship("KnowledgeNode", back_populates="subject")

    def __repr__(self):
        return f"<Subject(id={self.id}, name={self.name})>"