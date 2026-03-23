from typing import Optional, List

from pydantic import Field

from app.schemas.base import APIModel
from app.schemas.mixins.auditable import AuditableSchema
from app.db.models import NodeType, DifficultyLevel, RelationType


# ============================================
# NODE
# ============================================

class KnowledgeNodeCreate(APIModel):
    subject_id: int
    module_id: Optional[int] = None
    lesson_id: Optional[int] = None
    grade: int
    title: str
    description: Optional[str] = None
    node_type: NodeType = NodeType.CONCEPT
    difficulty_level: DifficultyLevel = DifficultyLevel.BASIC
    importance_weight: int = Field(default=1, ge=1, le=10)


class KnowledgeNodeUpdate(APIModel):
    title: Optional[str] = None
    description: Optional[str] = None
    node_type: Optional[NodeType] = None
    difficulty_level: Optional[DifficultyLevel] = None
    importance_weight: Optional[int] = Field(default=None, ge=1, le=10)
    module_id: Optional[int] = None
    lesson_id: Optional[int] = None


class KnowledgeEdgeCreate(APIModel):
    from_node_id: int
    to_node_id: int
    relation_type: RelationType


class KnowledgeNodeResponse(APIModel, AuditableSchema):
    id: int
    subject_id: int
    module_id: Optional[int] = None
    lesson_id: Optional[int] = None
    grade: int
    title: str
    description: Optional[str] = None
    node_type: NodeType
    difficulty_level: DifficultyLevel
    importance_weight: int


# ============================================
# EDGE
# ============================================

class KnowledgeEdgeCreate(APIModel):
    from_node_id: int
    to_node_id: int
    relation_type: RelationType


class KnowledgeEdgeResponse(APIModel, AuditableSchema):
    id: int
    from_node_id: int
    to_node_id: int
    relation_type: RelationType


# ============================================
# GRAPH
# ============================================

class SubgraphResponse(APIModel):
    nodes: List[KnowledgeNodeResponse]
    edges: List[KnowledgeEdgeResponse]


# ============================================
# MINDMAP (TREE STRUCTURE)
# ============================================

class MindmapNode(APIModel):
    id: int
    title: str
    node_type: NodeType
    difficulty_level: DifficultyLevel
    importance_weight: int
    children: List["MindmapNode"] = []


MindmapNode.model_rebuild()


class MindmapResponse(APIModel, AuditableSchema):
    id: int
    root_node_id: int
    structure: dict