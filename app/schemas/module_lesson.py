from typing import Optional

from pydantic import Field

from app.schemas.base import APIModel
from app.schemas.mixins.auditable import AuditableSchema


# ============================================
# MODULE SCHEMAS
# ============================================

class ModuleBase(APIModel):
    subject_id: int
    grade: int = Field(..., ge=1, le=12)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    display_order: int = 0


class ModuleCreate(ModuleBase):
    pass


class ModuleUpdate(APIModel):
    subject_id: Optional[int] = None
    grade: Optional[int] = Field(None, ge=1, le=12)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    display_order: Optional[int] = None


class ModuleResponse(ModuleBase, AuditableSchema):
    id: int


class ModuleWithLessons(ModuleResponse):
    """Module with lesson count"""
    lesson_count: int = 0


# ============================================
# LESSON SCHEMAS
# ============================================

class LessonBase(APIModel):
    module_id: int
    name: str = Field(..., min_length=1, max_length=200)
    content: Optional[str] = None
    display_order: int = 0


class LessonCreate(LessonBase):
    pass


class LessonUpdate(APIModel):
    module_id: Optional[int] = None
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = None
    display_order: Optional[int] = None


class LessonResponse(LessonBase, AuditableSchema):
    id: int


class LessonWithKnowledge(LessonResponse):
    """Lesson with knowledge node info"""
    knowledge_node_count: int = 0