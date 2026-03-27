from fastapi import APIRouter, Depends, Query, status
from typing import Optional
from app.db.models.user import User, UserRole
from app.schemas.module_lesson import (
    ModuleResponse,
    ModuleWithLessons,
)
from app.schemas.subject import (
    SubjectResponse,
    SubjectCreate,
    SubjectUpdate,
    SubjectWithStats,
)
from app.core.responses import success_response, paginated_response
from app.core.exceptions import ResourceNotFoundException
from app.api.deps import get_current_active_user, get_admin_user, require_any_role
from app.services.module_service import ModuleService, get_module_service
from app.services.subject_service import SubjectService, get_subject_service

router = APIRouter(prefix="/subjects", tags=["subjects"])

get_teacher_or_admin = require_any_role([UserRole.TEACHER, UserRole.ADMIN])


# ============================================
# PUBLIC / STUDENT ENDPOINTS
# ============================================


@router.get("", response_model=None)
async def list_subjects(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
    is_deleted: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by name or description"),
    current_user: User = Depends(get_current_active_user),
    subject_service: SubjectService = Depends(get_subject_service),
):
    """List all subjects. Accessible by all authenticated users."""
    subjects = subject_service.get_all(
        skip=skip, limit=limit, is_deleted=is_deleted, search=search
    )
    data = [
        SubjectResponse.model_validate(s).model_dump(by_alias=True) for s in subjects
    ]
    return success_response(data)


@router.get("/page", response_model=None)
async def page_subjects(
    page: int = Query(0, ge=0, description="Page number (0-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Page size (max 100)"),
    is_deleted: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by name or description"),
    current_user: User = Depends(get_current_active_user),
    subject_service: SubjectService = Depends(get_subject_service),
):
    """Paginated subject listing following api-design.md standards."""
    # Backend service uses 1-indexed page, API uses 0-indexed
    result = subject_service.page(
        page=page + 1, page_size=size, is_deleted=is_deleted, search=search
    )
    content = [
        SubjectResponse.model_validate(s).model_dump(by_alias=True) for s in result["data"]
    ]
    return paginated_response(
        content=content,
        page=page,
        size=size,
        total_elements=result["total"],
        total_pages=result["total_pages"],
    )


@router.get("/{subject_id}", response_model=None)
async def get_subject(
    subject_id: int,
    current_user: User = Depends(get_current_active_user),
    subject_service: SubjectService = Depends(get_subject_service),
):
    """Get subject by ID. Accessible by all authenticated users."""
    subject = subject_service.get_by_id(subject_id)
    if not subject:
        raise ResourceNotFoundException("Subject", subject_id)
    return success_response(
        SubjectResponse.model_validate(subject).model_dump(by_alias=True)
    )


@router.get("/{subject_id}/curriculum", response_model=None)
async def get_subject_curriculum(
    subject_id: int,
    current_user: User = Depends(get_current_active_user),
    module_service: ModuleService = Depends(get_module_service),
):
    """Get full curriculum (modules + lessons) for a subject."""
    modules = module_service.get_by_subject(subject_id)
    return success_response(
        [ModuleWithLessons.model_validate(m).model_dump(by_alias=True) for m in modules]
    )


@router.get("/{subject_id}/stats", response_model=None)
async def get_subject_stats(
    subject_id: int,
    current_user: User = Depends(get_current_active_user),
    subject_service: SubjectService = Depends(get_subject_service),
):
    """Get subject with statistics. Accessible by all authenticated users."""
    stats = subject_service.get_with_stats(subject_id)
    return success_response(
        SubjectWithStats.model_validate(stats).model_dump(by_alias=True)
    )


# ============================================
# TEACHER / ADMIN ENDPOINTS
# ============================================


@router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_subject(
    subject_data: SubjectCreate,
    current_user: User = Depends(get_teacher_or_admin),
    subject_service: SubjectService = Depends(get_subject_service),
):
    """Create a new subject. Requires: Teacher or Admin role."""
    subject = subject_service.create(subject_data)
    return success_response(
        SubjectResponse.model_validate(subject).model_dump(by_alias=True)
    )


@router.patch("/{subject_id}", response_model=None)
async def update_subject(
    subject_id: int,
    subject_data: SubjectUpdate,
    current_user: User = Depends(get_teacher_or_admin),
    subject_service: SubjectService = Depends(get_subject_service),
):
    """Update subject. Requires: Teacher or Admin role."""
    subject = subject_service.update(subject_id, subject_data)
    return success_response(
        SubjectResponse.model_validate(subject).model_dump(by_alias=True)
    )


@router.post("/{subject_id}/toggle-deleted", response_model=None)
async def toggle_subject_deleted(
    subject_id: int,
    current_user: User = Depends(get_teacher_or_admin),
    subject_service: SubjectService = Depends(get_subject_service),
):
    """Toggle subject deleted status. Requires: Teacher or Admin role."""
    subject = subject_service.toggle_deleted(subject_id)
    return success_response(
        SubjectResponse.model_validate(subject).model_dump(by_alias=True)
    )


# ============================================
# ADMIN ONLY ENDPOINTS
# ============================================


@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subject(
    subject_id: int,
    current_user: User = Depends(get_admin_user),
    subject_service: SubjectService = Depends(get_subject_service),
):
    """
    Delete subject permanently.

    Note: Will fail if subject has modules. Delete modules first or deactivate instead.
    Requires: Admin role only
    """
    subject_service.delete(subject_id)
    return None
