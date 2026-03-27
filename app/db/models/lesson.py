from sqlalchemy import Column, Integer, String, ForeignKey, Text, Table
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.models.base_model import BaseModel

# Association table for Lesson <-> KnowledgeNode (many-to-many)
lesson_knowledge = Table(
    'lesson_knowledge',
    Base.metadata,
    Column('lesson_id', Integer, ForeignKey('lessons.id', ondelete='CASCADE'), primary_key=True),
    Column('knowledge_node_id', Integer, ForeignKey('knowledge_nodes.id', ondelete='CASCADE'), primary_key=True),
    Column('display_order', Integer, default=0)
)


class Lesson(BaseModel):
    """Lesson model - Individual learning unit"""
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True, index=True)
    module_id = Column(Integer, ForeignKey("modules.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)  # Rich text content
    duration_mins = Column(Integer, nullable=True)
    display_order = Column(Integer, default=0)

    # Relationships
    module = relationship("Module", back_populates="lessons")
    knowledge_nodes = relationship(
        "KnowledgeNode",
        secondary=lesson_knowledge,
        back_populates="lessons"
    )

    def __repr__(self):
        return f"<Lesson(id={self.id}, name={self.name})>"