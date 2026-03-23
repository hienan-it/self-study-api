from fastapi import APIRouter, Depends, Query, status
from typing import List, Optional
from app.db.models.user import User, UserRole
from app.schemas.module_lesson import ModuleResponse, ModuleCreate, ModuleUpdate, ModuleWithLessons
from app.api.deps import get_current_active_user, get_admin_user, require_any_role
from app.services.module_service import ModuleService, get_module_service

router = APIRouter(prefix="/modules", tags=["modules"])

# Dependency for Teacher or Admin
get_teacher_or_admin = require_any_role([UserRole.TEACHER, UserRole.ADMIN])


# ============================================
# PUBLIC / STUDENT ENDPOINTS
# ============================================

@router.get("/", response_model=List[ModuleResponse])
async def list_modules(
        skip: int = Query(0, ge=0, description="Number of records to skip"),
        limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
        subject_id: Optional[int] = Query(None, description="Filter by subject ID"),
        grade: Optional[int] = Query(None, ge=1, le=12, description="Filter by grade (1-12)"),
        search: Optional[str] = Query(None, description="Search by name or description"),
        current_user: User = Depends(get_current_active_user),
        module_service: ModuleService = Depends(get_module_service)
):
    """
    List all modules with optional filters

    Accessible by: All authenticated users
    """
    return module_service.get_all(
        skip=skip,
        limit=limit,
        subject_id=subject_id,
        grade=grade,
        search=search
    )


@router.get("/grade/{grade}", response_model=List[ModuleResponse])
async def get_modules_by_grade(
        grade: int,
        current_user: User = Depends(get_current_active_user),
        module_service: ModuleService = Depends(get_module_service)
):
    """
    Get all modules for a specific grade

    Accessible by: All authenticated users
    """
    return module_service.get_by_grade(grade)


@router.get("/{module_id}", response_model=ModuleResponse)
async def get_module(
        module_id: int,
        current_user: User = Depends(get_current_active_user),
        module_service: ModuleService = Depends(get_module_service)
):
    """
    Get module by ID

    Accessible by: All authenticated users
    """
    module = module_service.get_by_id(module_id)
    if not module:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module with id {module_id} not found"
        )
    return module


@router.get("/{module_id}/details", response_model=ModuleWithLessons)
async def get_module_details(
        module_id: int,
        current_user: User = Depends(get_current_active_user),
        module_service: ModuleService = Depends(get_module_service)
):
    """
    Get module with lesson count

    Accessible by: All authenticated users
    """
    return module_service.get_with_lesson_count(module_id)


# ============================================
# TEACHER / ADMIN ENDPOINTS
# ============================================

@router.post("/", response_model=ModuleResponse, status_code=status.HTTP_201_CREATED)
async def create_module(
        module_data: ModuleCreate,
        current_user: User = Depends(get_teacher_or_admin),
        module_service: ModuleService = Depends(get_module_service)
):
    """
    Create a new module

    Requires: Teacher or Admin role
    """
    return module_service.create(module_data)


@router.patch("/{module_id}", response_model=ModuleResponse)
async def update_module(
        module_id: int,
        module_data: ModuleUpdate,
        current_user: User = Depends(get_teacher_or_admin),
        module_service: ModuleService = Depends(get_module_service)
):
    """
    Update module

    Requires: Teacher or Admin role
    """
    return module_service.update(module_id, module_data)


@router.patch("/{module_id}/reorder", response_model=ModuleResponse)
async def reorder_module(
        module_id: int,
        new_order: int = Query(..., ge=0, description="New display order"),
        current_user: User = Depends(get_teacher_or_admin),
        module_service: ModuleService = Depends(get_module_service)
):
    """
    Update module display order

    Requires: Teacher or Admin role
    """
    return module_service.reorder(module_id, new_order)


# ============================================
# ADMIN ONLY ENDPOINTS
# ============================================

@router.delete("/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module(
        module_id: int,
        current_user: User = Depends(get_admin_user),
        module_service: ModuleService = Depends(get_module_service)
):
    """
    Delete module permanently

    Note: Will fail if module has lessons. Delete lessons first.

    Requires: Admin role only
    """
    module_service.delete(module_id)
    return None