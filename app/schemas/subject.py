from typing import Optional
from pydantic import Field

from app.schemas.base import APIModel
from app.schemas.mixins.auditable import AuditableSchema


from app.schemas.mixins.soft_delete import SoftDeletableSchema


class SubjectBase(APIModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class SubjectCreate(SubjectBase):
    pass


class SubjectUpdate(APIModel, SoftDeletableSchema):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None


class SubjectResponse(SubjectBase, AuditableSchema, SoftDeletableSchema):
    id: int


class SubjectWithStats(SubjectResponse):
    """Subject with statistics"""
    module_count: int = 0
    lesson_count: int = 0
    knowledge_node_count: int = 0