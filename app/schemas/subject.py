from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class SubjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: bool = True


class SubjectCreate(SubjectBase):
    pass


class SubjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SubjectResponse(SubjectBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SubjectWithStats(SubjectResponse):
    """Subject with statistics"""
    module_count: int = 0
    lesson_count: int = 0
    knowledge_node_count: int = 0

    class Config:
        from_attributes = True