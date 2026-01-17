from functools import wraps
from fastapi import HTTPException, status
from app.models.user import User, UserRole
from typing import Callable, List


def is_authenticated():
    """Decorator to check if user is authenticated"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, current_user: User = None, **kwargs):
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated"
                )
            if not current_user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Inactive user"
                )
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator


def has_role(required_role: UserRole):
    """Decorator to check if user has a specific role"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, current_user: User = None, **kwargs):
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated"
                )
            if not current_user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Inactive user"
                )
            if current_user.role != required_role:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Required role: {required_role.value}"
                )
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator


def has_any_role(required_roles: List[UserRole]):
    """Decorator to check if user has any of the specified roles"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, current_user: User = None, **kwargs):
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated"
                )
            if not current_user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Inactive user"
                )
            if not current_user.has_any_role(required_roles):
                role_names = [role.value for role in required_roles]
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Required one of roles: {', '.join(role_names)}"
                )
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator


def has_all_roles(required_roles: List[UserRole]):
    """Decorator to check if user has all specified roles (for future multi-role support)"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, current_user: User = None, **kwargs):
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated"
                )
            if not current_user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Inactive user"
                )
            if not current_user.has_all_roles(required_roles):
                role_names = [role.value for role in required_roles]
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Required all roles: {', '.join(role_names)}"
                )
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator