from fastapi import APIRouter, Depends, Query, status
from typing import Optional
from app.db.models.user import User, UserRole
from app.schemas.module_lesson import (
    LessonResponse,
    LessonCreate,
    LessonUpdate,
    LessonWithKnowledge,
)
from app.core.responses import success_response, paginated_response
from app.core.exceptions import ResourceNotFoundException
from app.api.deps import get_current_active_user, get_admin_user, require_any_role
from app.services.lesson_service import LessonService, get_lesson_service

router = APIRouter(prefix="/lessons", tags=["lessons"])

get_teacher_or_admin = require_any_role([UserRole.TEACHER, UserRole.ADMIN])


# ============================================
# PUBLIC / STUDENT ENDPOINTS
# ============================================


@router.get("", response_model=None)
async def list_lessons(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
    module_id: Optional[int] = Query(None, description="Filter by module ID"),
    search: Optional[str] = Query(None, description="Search by name or content"),
    current_user: User = Depends(get_current_active_user),
    lesson_service: LessonService = Depends(get_lesson_service),
):
    """List all lessons. Accessible by all authenticated users."""
    lessons = lesson_service.get_all(
    )
    return success_response(
        [
            LessonResponse.model_validate(lesson).model_dump(by_alias=True)
            for lesson in lessons
        ]
    )


@router.get("/page", response_model=None)
async def page_lessons(
    page: int = Query(0, ge=0, description="Page number (0-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Page size (max 100)"),
    module_id: Optional[int] = Query(None, description="Filter by module ID"),
    search: Optional[str] = Query(None, description="Search by name or content"),
    current_user: User = Depends(get_current_active_user),
    lesson_service: LessonService = Depends(get_lesson_service),
):
    """Paginated lesson listing following api-design.md standards."""
    result = lesson_service.page(
        page=page + 1, page_size=size, module_id=module_id, search=search
    )
    content = [
        LessonResponse.model_validate(lesson).model_dump(by_alias=True)
        for lesson in result["data"]
    ]
    return paginated_response(
        content=content,
        page=page,
        size=size,
        total_elements=result["total"],
        total_pages=result["total_pages"],
    )


@router.get("/{lesson_id}", response_model=None)
async def get_lesson(
    lesson_id: int,
    current_user: User = Depends(get_current_active_user),
    lesson_service: LessonService = Depends(get_lesson_service),
):
    """Get lesson by ID. Accessible by all authenticated users."""
    lesson = lesson_service.get_by_id(lesson_id)
    if not lesson:
        raise ResourceNotFoundException("Lesson", lesson_id)
    return success_response(
        LessonResponse.model_validate(lesson).model_dump(by_alias=True)
    )


@router.get("/{lesson_id}/details", response_model=None)
async def get_lesson_details(
    lesson_id: int,
    current_user: User = Depends(get_current_active_user),
    lesson_service: LessonService = Depends(get_lesson_service),
):
    """Get lesson with knowledge node count. Accessible by all authenticated users."""
    lesson = lesson_service.get_with_knowledge_count(lesson_id)
    return success_response(
        LessonWithKnowledge.model_validate(lesson).model_dump(by_alias=True)
    )


# ============================================
# TEACHER / ADMIN ENDPOINTS
# ============================================


@router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_lesson(
    lesson_data: LessonCreate,
    current_user: User = Depends(get_teacher_or_admin),
    lesson_service: LessonService = Depends(get_lesson_service),
):
    """Create a new lesson. Requires: Teacher or Admin role."""
    lesson = lesson_service.create(lesson_data)
    return success_response(
        LessonResponse.model_validate(lesson).model_dump(by_alias=True)
    )


@router.patch("/{lesson_id}", response_model=None)
async def update_lesson(
    lesson_id: int,
    lesson_data: LessonUpdate,
    current_user: User = Depends(get_teacher_or_admin),
    lesson_service: LessonService = Depends(get_lesson_service),
):
    """Update lesson. Requires: Teacher or Admin role."""
    lesson = lesson_service.update(lesson_id, lesson_data)
    return success_response(
        LessonResponse.model_validate(lesson).model_dump(by_alias=True)
    )


@router.patch("/{lesson_id}/reorder", response_model=None)
async def reorder_lesson(
    lesson_id: int,
    new_order: int = Query(..., ge=0, description="New display order"),
    current_user: User = Depends(get_teacher_or_admin),
    lesson_service: LessonService = Depends(get_lesson_service),
):
    """Update lesson display order. Requires: Teacher or Admin role."""
    lesson = lesson_service.reorder(lesson_id, new_order)
    return success_response(
        LessonResponse.model_validate(lesson).model_dump(by_alias=True)
    )


# ============================================
# ADMIN ONLY ENDPOINTS
# ============================================


@router.delete("/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lesson(
    lesson_id: int,
    current_user: User = Depends(get_admin_user),
    lesson_service: LessonService = Depends(get_lesson_service),
):
    """Delete lesson permanently. Requires: Admin role only."""
    lesson_service.delete(lesson_id)
    return None
