from fastapi import APIRouter, Depends, Query, status
from typing import List, Optional
from app.models.user import User, UserRole
from app.schemas.subject import SubjectResponse, SubjectCreate, SubjectUpdate, SubjectWithStats
from app.api.deps import get_current_active_user, get_admin_user, require_any_role
from app.services.subject_service import SubjectService, get_subject_service

router = APIRouter(prefix="/subjects", tags=["subjects"])

# Dependency for Teacher or Admin
get_teacher_or_admin = require_any_role([UserRole.TEACHER, UserRole.ADMIN])


# ============================================
# PUBLIC / STUDENT ENDPOINTS
# ============================================

@router.get("/", response_model=List[SubjectResponse])
async def list_subjects(
        skip: int = Query(0, ge=0, description="Number of records to skip"),
        limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
        is_active: Optional[bool] = Query(None, description="Filter by active status"),
        search: Optional[str] = Query(None, description="Search by name or description"),
        current_user: User = Depends(get_current_active_user),
        subject_service: SubjectService = Depends(get_subject_service)
):
    """
    List all subjects with optional filters

    Accessible by: All authenticated users
    """
    return subject_service.get_all(
        skip=skip,
        limit=limit,
        is_active=is_active,
        search=search
    )


@router.get("/{subject_id}", response_model=SubjectResponse)
async def get_subject(
        subject_id: int,
        current_user: User = Depends(get_current_active_user),
        subject_service: SubjectService = Depends(get_subject_service)
):
    """
    Get subject by ID

    Accessible by: All authenticated users
    """
    subject = subject_service.get_by_id(subject_id)
    if not subject:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject with id {subject_id} not found"
        )
    return subject


@router.get("/{subject_id}/stats", response_model=SubjectWithStats)
async def get_subject_stats(
        subject_id: int,
        current_user: User = Depends(get_current_active_user),
        subject_service: SubjectService = Depends(get_subject_service)
):
    """
    Get subject with statistics (module count, lesson count, etc.)

    Accessible by: All authenticated users
    """
    return subject_service.get_with_stats(subject_id)


# ============================================
# TEACHER / ADMIN ENDPOINTS
# ============================================

@router.post("/", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
async def create_subject(
        subject_data: SubjectCreate,
        current_user: User = Depends(get_teacher_or_admin),
        subject_service: SubjectService = Depends(get_subject_service)
):
    """
    Create a new subject

    Requires: Teacher or Admin role
    """
    return subject_service.create(subject_data)


@router.patch("/{subject_id}", response_model=SubjectResponse)
async def update_subject(
        subject_id: int,
        subject_data: SubjectUpdate,
        current_user: User = Depends(get_teacher_or_admin),
        subject_service: SubjectService = Depends(get_subject_service)
):
    """
    Update subject

    Requires: Teacher or Admin role
    """
    return subject_service.update(subject_id, subject_data)


@router.post("/{subject_id}/toggle-active", response_model=SubjectResponse)
async def toggle_subject_active(
        subject_id: int,
        current_user: User = Depends(get_teacher_or_admin),
        subject_service: SubjectService = Depends(get_subject_service)
):
    """
    Toggle subject active status

    Requires: Teacher or Admin role
    """
    return subject_service.toggle_active(subject_id)


# ============================================
# ADMIN ONLY ENDPOINTS
# ============================================

@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subject(
        subject_id: int,
        current_user: User = Depends(get_admin_user),
        subject_service: SubjectService = Depends(get_subject_service)
):
    """
    Delete subject permanently

    Note: Will fail if subject has modules. Delete modules first or deactivate instead.

    Requires: Admin role only
    """
    subject_service.delete(subject_id)
    return None