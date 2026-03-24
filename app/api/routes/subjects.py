from fastapi import APIRouter, Depends, Query, status
from typing import Optional
from app.db.models.user import User, UserRole
from app.schemas.subject import (
    SubjectResponse,
    SubjectCreate,
    SubjectUpdate,
    SubjectWithStats,
)
from app.core.responses import success_response
from app.core.exceptions import ResourceNotFoundException
from app.api.deps import get_current_active_user, get_admin_user, require_any_role
from app.services.subject_service import SubjectService, get_subject_service

router = APIRouter(prefix="/subjects", tags=["subjects"])

get_teacher_or_admin = require_any_role([UserRole.TEACHER, UserRole.ADMIN])


# ============================================
# PUBLIC / STUDENT ENDPOINTS
# ============================================


@router.get("/", response_model=None)
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


@router.post("/", response_model=None, status_code=status.HTTP_201_CREATED)
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


@router.post("/{subject_id}/toggle-active", response_model=None)
async def toggle_subject_active(
    subject_id: int,
    current_user: User = Depends(get_teacher_or_admin),
    subject_service: SubjectService = Depends(get_subject_service),
):
    """Toggle subject active status. Requires: Teacher or Admin role."""
    subject = subject_service.toggle_active(subject_id)
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
