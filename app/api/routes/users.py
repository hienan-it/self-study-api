from fastapi import APIRouter, Depends, Query
from typing import Optional
from app.db.models.user import User, UserRole
from app.schemas.user import UserResponse, UserUpdate, UserCreate
from app.core.responses import success_response, paginated_response
from app.core.exceptions import ResourceNotFoundException, BusinessRuleException
from app.api.deps import get_current_active_user, get_admin_user, get_teacher_or_admin
from app.services.user_service import UserService, get_user_service

router = APIRouter(prefix="/users", tags=["users"])


# ============================================
# CURRENT USER ENDPOINTS
# ============================================


@router.get("/me", response_model=None)
async def read_current_user(current_user: User = Depends(get_current_active_user)):
    """Get current authenticated user profile"""
    return success_response(
        UserResponse.model_validate(current_user).model_dump(by_alias=True)
    )


@router.patch("/me", response_model=None)
async def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service),
):
    """Update current user's own profile (limited fields)"""
    # Users cannot change their own role or active status via this endpoint
    if user_update.role is not None and current_user.role != UserRole.ADMIN:
        user_update.role = None  # Ignore role change for non-admins

    if user_update.isActive is not None:
        user_update.isActive = None  # Users cannot deactivate themselves here

    updated = user_service.update(current_user.id, user_update)
    return success_response(
        UserResponse.model_validate(updated).model_dump(by_alias=True)
    )


# ============================================
# USER LISTING & SEARCH (Teacher/Admin)
# ============================================


@router.get("/", response_model=None)
async def list_users(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
    role: Optional[UserRole] = Query(None, description="Filter by role"),
    is_deleted: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by username or email"),
    current_user: User = Depends(get_teacher_or_admin),
    user_service: UserService = Depends(get_user_service),
):
    """
    List all users with optional filters

    Requires: Teacher or Admin role
    """
    users = user_service.get_all(
        skip=skip, limit=limit, role=role, is_deleted=is_deleted, search=search
    )
    data = [UserResponse.model_validate(u).model_dump(by_alias=True) for u in users]
    return success_response(data)


@router.get("/page/", response_model=None)
async def page_users(
    page: int = Query(0, ge=0, description="Page number (0-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Page size (max 100)"),
    role: Optional[UserRole] = Query(None, description="Filter by role"),
    is_deleted: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by username or email"),
    current_user: User = Depends(get_teacher_or_admin),
    user_service: UserService = Depends(get_user_service),
):
    """
    Paginated user listing

    Requires: Teacher or Admin role
    """
    result = user_service.page(
        page=page, page_size=page_size, role=role, is_deleted=is_deleted, search=search
    )
    content = [
        UserResponse.model_validate(u).model_dump(by_alias=True) for u in result.content
    ]
    return paginated_response(
        content=content,
        page=result.page,
        size=result.size,
        total_elements=result.total_elements,
        total_pages=result.total_pages,
    )


@router.get("/count", response_model=None)
async def count_users(
    role: Optional[UserRole] = Query(None, description="Filter by role"),
    is_deleted: Optional[bool] = Query(None, description="Filter by active status"),
    current_user: User = Depends(get_teacher_or_admin),
    user_service: UserService = Depends(get_user_service),
):
    """
    Get user statistics

    Returns total count and breakdown by role and status
    """
    return success_response(user_service.count_users(role=role, is_deleted=is_deleted))


@router.get("/{user_id}", response_model=None)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_teacher_or_admin),
    user_service: UserService = Depends(get_user_service),
):
    """
    Get user by ID

    Requires: Teacher or Admin role
    """
    user = user_service.get_by_id(user_id)
    if not user:
        raise ResourceNotFoundException("User", user_id)
    return success_response(UserResponse.model_validate(user).model_dump(by_alias=True))


# ============================================
# USER MANAGEMENT (Admin Only)
# ============================================


@router.post("/", response_model=None, status_code=201)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(get_admin_user),
    user_service: UserService = Depends(get_user_service),
):
    """
    Create a new user

    Requires: Admin role
    """
    user = user_service.create(user_data)
    return success_response(UserResponse.model_validate(user).model_dump(by_alias=True))


@router.patch("/{user_id}", response_model=None)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: User = Depends(get_admin_user),
    user_service: UserService = Depends(get_user_service),
):
    """
    Update any user (including role and active status)

    Requires: Admin role
    """
    # Prevent admin from deactivating themselves
    if user_id == current_user.id and user_update.isActive is False:
        raise BusinessRuleException("Cannot deactivate yourself")

    updated = user_service.update(user_id, user_update)
    return success_response(
        UserResponse.model_validate(updated).model_dump(by_alias=True)
    )


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_admin_user),
    user_service: UserService = Depends(get_user_service),
):
    """
    Delete user permanently

    Requires: Admin role
    """
    user_service.delete(user_id, current_user.id)
    return None


# ============================================
# USER ACTIVATION/DEACTIVATION (Admin Only)
# ============================================


@router.post("/{user_id}/deactivate", response_model=None)
async def deactivate_user(
    user_id: int,
    current_user: User = Depends(get_admin_user),
    user_service: UserService = Depends(get_user_service),
):
    """
    Deactivate user (soft delete)

    Requires: Admin role
    """
    user = user_service.deactivate(user_id, current_user.id)
    return success_response(UserResponse.model_validate(user).model_dump(by_alias=True))


@router.post("/{user_id}/activate", response_model=None)
async def activate_user(
    user_id: int,
    current_user: User = Depends(get_admin_user),
    user_service: UserService = Depends(get_user_service),
):
    """
    Activate a deactivated user

    Requires: Admin role
    """
    user = user_service.activate(user_id)
    return success_response(UserResponse.model_validate(user).model_dump(by_alias=True))
