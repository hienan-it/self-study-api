from sqlalchemy import Column, Integer, String, ForeignKey, Text
from sqlalchemy.orm import relationship
import enum

from app.db.models.base_model import BaseModel
from app.db.models.lesson import lesson_knowledge
from app.utils.enum_as_string import EnumAsString


class NodeType(str, enum.Enum):
    """Types of knowledge nodes"""
    CONCEPT = "concept"
    FORMULA = "formula"
    THEOREM = "theorem"
    EXAMPLE = "example"
    DEFINITION = "definition"
    PROCEDURE = "procedure"
    FACT = "fact"
    VIRTUAL = "virtual"


class DifficultyLevel(str, enum.Enum):
    """Difficulty levels"""
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class RelationType(str, enum.Enum):
    """Types of relationships between knowledge nodes"""
    PREREQUISITE = "prerequisite"  # A requires B
    BUILDS_ON = "builds_on"  # A builds on B
    RELATES_TO = "relates_to"  # A relates to B
    EXAMPLE_OF = "example_of"  # A is example of B
    PART_OF = "part_of"  # A is part of B
    DEFINITION = "definition"
    PROCEDURE = "procedure_of"


class KnowledgeNode(BaseModel):
    """Knowledge Graph Node - Represents a knowledge concept"""
    __tablename__ = "knowledge_nodes"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    module_id = Column(Integer, ForeignKey("modules.id", ondelete="CASCADE"), nullable=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True)
    grade = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    node_type = Column(EnumAsString(NodeType), default=NodeType.CONCEPT, nullable=False)
    difficulty_level = Column(EnumAsString(DifficultyLevel), default=DifficultyLevel.BASIC, nullable=False)
    importance_weight = Column(Integer, default=1)  # 1-10 scale

    # Relationships
    subject = relationship("Subject", back_populates="knowledge_nodes")
    module = relationship("Module", back_populates="knowledge_nodes")
    lessons = relationship("Lesson", secondary=lesson_knowledge, back_populates="knowledge_nodes")

    # Self-referential relationships via edges
    outgoing_edges = relationship(
        "KnowledgeEdge",
        foreign_keys="KnowledgeEdge.from_node_id",
        back_populates="from_node",
        cascade="all, delete-orphan"
    )
    incoming_edges = relationship(
        "KnowledgeEdge",
        foreign_keys="KnowledgeEdge.to_node_id",
        back_populates="to_node",
        cascade="all, delete-orphan"
    )
    enrichment = relationship(
        "KnowledgeNodeEnrichment",
        back_populates="node",
        uselist=False,
        cascade="all, delete-orphan",
    )

    questions = relationship("Question", back_populates="knowledge_node", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<KnowledgeNode(id={self.id}, title={self.title}, type={self.node_type})>"


class KnowledgeEdge(BaseModel):
    """Knowledge Graph Edge - Represents relationship between nodes"""
    __tablename__ = "knowledge_edges"

    id = Column(Integer, primary_key=True, index=True)
    from_node_id = Column(Integer, ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False)
    to_node_id = Column(Integer, ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(EnumAsString(RelationType), nullable=False)

    # Relationships
    from_node = relationship("KnowledgeNode", foreign_keys=[from_node_id], back_populates="outgoing_edges")
    to_node = relationship("KnowledgeNode", foreign_keys=[to_node_id], back_populates="incoming_edges")

    def __repr__(self):
        return f"<KnowledgeEdge(from={self.from_node_id}, to={self.to_node_id}, type={self.relation_type})>"


class KnowledgeNodeEnrichment(BaseModel):
    """
    Cache LLM enrichment cho từng KnowledgeNode.

    - 1-1 với KnowledgeNode (unique constraint trên knowledge_node_id)
    - Một khi đã enrich, không cần gọi LLM lại cho node đó nữa
    - Nếu node description thay đổi → xóa enrichment để trigger re-enrich
    """
    __tablename__ = "knowledge_node_enrichments"

    id = Column(Integer, primary_key=True, index=True)
    knowledge_node_id = Column(
        Integer,
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # 1-1 với KnowledgeNode
        index=True,
    )
    learning_note = Column(Text, nullable=True)
    memory_tip = Column(Text, nullable=True)
    key_formula = Column(Text, nullable=True)
    difficulty_note = Column(Text, nullable=True)

    # Relationship ngược lại để dễ access từ KnowledgeNode
    node = relationship("KnowledgeNode", back_populates="enrichment")

    def __repr__(self):
        return f"<KnowledgeNodeEnrichment(node_id={self.knowledge_node_id})>"