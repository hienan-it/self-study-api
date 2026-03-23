from fastapi import APIRouter, Depends, Query, status
from typing import List, Optional
from app.db.models.user import User, UserRole
from app.schemas.module_lesson import LessonResponse, LessonCreate, LessonUpdate, LessonWithKnowledge
from app.api.deps import get_current_active_user, get_admin_user, require_any_role
from app.services.lesson_service import LessonService, get_lesson_service

router = APIRouter(prefix="/lessons", tags=["lessons"])

# Dependency for Teacher or Admin
get_teacher_or_admin = require_any_role([UserRole.TEACHER, UserRole.ADMIN])


# ============================================
# PUBLIC / STUDENT ENDPOINTS
# ============================================

@router.get("/", response_model=List[LessonResponse])
async def list_lessons(
        skip: int = Query(0, ge=0, description="Number of records to skip"),
        limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
        module_id: Optional[int] = Query(None, description="Filter by module ID"),
        search: Optional[str] = Query(None, description="Search by name or content"),
        current_user: User = Depends(get_current_active_user),
        lesson_service: LessonService = Depends(get_lesson_service)
):
    """
    List all lessons with optional filters

    Accessible by: All authenticated users
    """
    return lesson_service.get_all(
        skip=skip,
        limit=limit,
        module_id=module_id,
        search=search
    )


@router.get("/{lesson_id}", response_model=LessonResponse)
async def get_lesson(
        lesson_id: int,
        current_user: User = Depends(get_current_active_user),
        lesson_service: LessonService = Depends(get_lesson_service)
):
    """
    Get lesson by ID

    Accessible by: All authenticated users
    """
    lesson = lesson_service.get_by_id(lesson_id)
    if not lesson:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson with id {lesson_id} not found"
        )
    return lesson


@router.get("/{lesson_id}/details", response_model=LessonWithKnowledge)
async def get_lesson_details(
        lesson_id: int,
        current_user: User = Depends(get_current_active_user),
        lesson_service: LessonService = Depends(get_lesson_service)
):
    """
    Get lesson with knowledge node count

    Accessible by: All authenticated users
    """
    return lesson_service.get_with_knowledge_count(lesson_id)


# ============================================
# TEACHER / ADMIN ENDPOINTS
# ============================================

@router.post("/", response_model=LessonResponse, status_code=status.HTTP_201_CREATED)
async def create_lesson(
        lesson_data: LessonCreate,
        current_user: User = Depends(get_teacher_or_admin),
        lesson_service: LessonService = Depends(get_lesson_service)
):
    """
    Create a new lesson

    Requires: Teacher or Admin role
    """
    return lesson_service.create(lesson_data)


@router.patch("/{lesson_id}", response_model=LessonResponse)
async def update_lesson(
        lesson_id: int,
        lesson_data: LessonUpdate,
        current_user: User = Depends(get_teacher_or_admin),
        lesson_service: LessonService = Depends(get_lesson_service)
):
    """
    Update lesson

    Requires: Teacher or Admin role
    """
    return lesson_service.update(lesson_id, lesson_data)


@router.patch("/{lesson_id}/reorder", response_model=LessonResponse)
async def reorder_lesson(
        lesson_id: int,
        new_order: int = Query(..., ge=0, description="New display order"),
        current_user: User = Depends(get_teacher_or_admin),
        lesson_service: LessonService = Depends(get_lesson_service)
):
    """
    Update lesson display order

    Requires: Teacher or Admin role
    """
    return lesson_service.reorder(lesson_id, new_order)


# ============================================
# ADMIN ONLY ENDPOINTS
# ============================================

@router.delete("/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lesson(
        lesson_id: int,
        current_user: User = Depends(get_admin_user),
        lesson_service: LessonService = Depends(get_lesson_service)
):
    """
    Delete lesson permanently

    Requires: Admin role only
    """
    lesson_service.delete(lesson_id)
    return None