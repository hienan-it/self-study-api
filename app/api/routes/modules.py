from fastapi import APIRouter, Depends, Query, status
from typing import Optional
from app.db.models.user import User, UserRole
from app.schemas.module_lesson import (
    ModuleResponse,
    ModuleCreate,
    ModuleUpdate,
    ModuleWithLessons,
)
from app.core.responses import success_response
from app.core.exceptions import ResourceNotFoundException
from app.api.deps import get_current_active_user, get_admin_user, require_any_role
from app.services.module_service import ModuleService, get_module_service

router = APIRouter(prefix="/modules", tags=["modules"])

get_teacher_or_admin = require_any_role([UserRole.TEACHER, UserRole.ADMIN])


# ============================================
# PUBLIC / STUDENT ENDPOINTS
# ============================================


@router.get("/", response_model=None)
async def list_modules(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
    subject_id: Optional[int] = Query(None, description="Filter by subject ID"),
    grade: Optional[int] = Query(
        None, ge=1, le=12, description="Filter by grade (1-12)"
    ),
    search: Optional[str] = Query(None, description="Search by name or description"),
    current_user: User = Depends(get_current_active_user),
    module_service: ModuleService = Depends(get_module_service),
):
    """List all modules. Accessible by all authenticated users."""
    modules = module_service.get_all(
        skip=skip, limit=limit, subject_id=subject_id, grade=grade, search=search
    )
    return success_response(
        [ModuleResponse.model_validate(m).model_dump(by_alias=True) for m in modules]
    )


@router.get("/grade/{grade}", response_model=None)
async def get_modules_by_grade(
    grade: int,
    current_user: User = Depends(get_current_active_user),
    module_service: ModuleService = Depends(get_module_service),
):
    """Get all modules for a specific grade. Accessible by all authenticated users."""
    modules = module_service.get_by_grade(grade)
    return success_response(
        [ModuleResponse.model_validate(m).model_dump(by_alias=True) for m in modules]
    )


@router.get("/{module_id}", response_model=None)
async def get_module(
    module_id: int,
    current_user: User = Depends(get_current_active_user),
    module_service: ModuleService = Depends(get_module_service),
):
    """Get module by ID. Accessible by all authenticated users."""
    module = module_service.get_by_id(module_id)
    if not module:
        raise ResourceNotFoundException("Module", module_id)
    return success_response(
        ModuleResponse.model_validate(module).model_dump(by_alias=True)
    )


@router.get("/{module_id}/details", response_model=None)
async def get_module_details(
    module_id: int,
    current_user: User = Depends(get_current_active_user),
    module_service: ModuleService = Depends(get_module_service),
):
    """Get module with lesson count. Accessible by all authenticated users."""
    module = module_service.get_with_lesson_count(module_id)
    return success_response(
        ModuleWithLessons.model_validate(module).model_dump(by_alias=True)
    )


# ============================================
# TEACHER / ADMIN ENDPOINTS
# ============================================


@router.post("/", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_module(
    module_data: ModuleCreate,
    current_user: User = Depends(get_teacher_or_admin),
    module_service: ModuleService = Depends(get_module_service),
):
    """Create a new module. Requires: Teacher or Admin role."""
    module = module_service.create(module_data)
    return success_response(
        ModuleResponse.model_validate(module).model_dump(by_alias=True)
    )


@router.patch("/{module_id}", response_model=None)
async def update_module(
    module_id: int,
    module_data: ModuleUpdate,
    current_user: User = Depends(get_teacher_or_admin),
    module_service: ModuleService = Depends(get_module_service),
):
    """Update module. Requires: Teacher or Admin role."""
    module = module_service.update(module_id, module_data)
    return success_response(
        ModuleResponse.model_validate(module).model_dump(by_alias=True)
    )


@router.patch("/{module_id}/reorder", response_model=None)
async def reorder_module(
    module_id: int,
    new_order: int = Query(..., ge=0, description="New display order"),
    current_user: User = Depends(get_teacher_or_admin),
    module_service: ModuleService = Depends(get_module_service),
):
    """Update module display order. Requires: Teacher or Admin role."""
    module = module_service.reorder(module_id, new_order)
    return success_response(
        ModuleResponse.model_validate(module).model_dump(by_alias=True)
    )


# ============================================
# ADMIN ONLY ENDPOINTS
# ============================================


@router.delete("/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module(
    module_id: int,
    current_user: User = Depends(get_admin_user),
    module_service: ModuleService = Depends(get_module_service),
):
    """Delete module permanently. Requires: Admin role only."""
    module_service.delete(module_id)
    return None
