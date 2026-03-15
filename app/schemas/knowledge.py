from typing import Optional, List

from pydantic import BaseModel, Field
from datetime import datetime

from app.models import NodeType, DifficultyLevel, RelationType


class KnowledgeNodeCreate(BaseModel):
    subject_id: int
    module_id: Optional[int] = None
    lesson_id: Optional[int] = None
    grade: int
    title: str
    description: Optional[str] = None
    node_type: NodeType = NodeType.CONCEPT
    difficulty_level: DifficultyLevel = DifficultyLevel.BASIC
    importance_weight: int = Field(default=1, ge=1, le=10)


class KnowledgeNodeUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    node_type: Optional[NodeType] = None
    difficulty_level: Optional[DifficultyLevel] = None
    importance_weight: Optional[int] = Field(default=None, ge=1, le=10)
    module_id: Optional[int] = None
    lesson_id: Optional[int] = None


class KnowledgeEdgeCreate(BaseModel):
    from_node_id: int
    to_node_id: int
    relation_type: RelationType


class KnowledgeNodeResponse(BaseModel):
    id: int
    subject_id: int
    module_id: Optional[int]
    lesson_id: Optional[int]
    grade: int
    title: str
    description: Optional[str]
    node_type: NodeType
    difficulty_level: DifficultyLevel
    importance_weight: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class KnowledgeEdgeResponse(BaseModel):
    id: int
    from_node_id: int
    to_node_id: int
    relation_type: RelationType
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class SubgraphResponse(BaseModel):
    nodes: List[KnowledgeNodeResponse]
    edges: List[KnowledgeEdgeResponse]


class MindmapNode(BaseModel):
    id: int
    title: str
    node_type: NodeType
    difficulty_level: DifficultyLevel
    importance_weight: int
    children: List["MindmapNode"]


MindmapNode.model_rebuild()


class MindmapResponse(BaseModel):
    id: int
    root_node_id: int
    structure: dict
    created_at: Optional[datetime]

    class Config:
        from_attributes = True