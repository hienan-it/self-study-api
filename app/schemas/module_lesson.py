from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


# ============================================
# MODULE SCHEMAS
# ============================================

class ModuleBase(BaseModel):
    subject_id: int
    grade: int = Field(..., ge=1, le=12)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    display_order: int = 0


class ModuleCreate(ModuleBase):
    pass


class ModuleUpdate(BaseModel):
    subject_id: Optional[int] = None
    grade: Optional[int] = Field(None, ge=1, le=12)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    display_order: Optional[int] = None


class ModuleResponse(ModuleBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ModuleWithLessons(ModuleResponse):
    """Module with lesson count"""
    lesson_count: int = 0

    class Config:
        from_attributes = True


# ============================================
# LESSON SCHEMAS
# ============================================

class LessonBase(BaseModel):
    module_id: int
    name: str = Field(..., min_length=1, max_length=200)
    content: Optional[str] = None
    display_order: int = 0


class LessonCreate(LessonBase):
    pass


class LessonUpdate(BaseModel):
    module_id: Optional[int] = None
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = None
    display_order: Optional[int] = None


class LessonResponse(LessonBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LessonWithKnowledge(LessonResponse):
    """Lesson with knowledge node info"""
    knowledge_node_count: int = 0

    class Config:
        from_attributes = True