from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.db.models.user import User, UserRole
from app.core.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


async def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db)
) -> User:
    """Get current user from JWT token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    username = decode_access_token(token)
    if username is None:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
        current_user: User = Depends(get_current_user)
) -> User:
    """Check if current user is active"""
    if current_user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user


# ============================================
# ROLE-BASED DEPENDENCY FUNCTIONS
# ============================================

def require_role(required_role: UserRole):
    """Dependency to require a specific role"""

    async def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: {required_role.value}"
            )
        return current_user

    return role_checker


def require_any_role(required_roles: List[UserRole]):
    """Dependency to require any of the specified roles"""

    async def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role not in required_roles:
            role_names = [role.value for role in required_roles]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required one of roles: {', '.join(role_names)}"
            )
        return current_user

    return role_checker


def require_all_roles(required_roles: List[UserRole]):
    """Dependency to require all specified roles (for future multi-role support)"""

    async def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        if not all(current_user.has_role(role) for role in required_roles):
            role_names = [role.value for role in required_roles]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required all roles: {', '.join(role_names)}"
            )
        return current_user

    return role_checker


# ============================================
# SHORTCUT DEPENDENCIES FOR COMMON ROLES
# ============================================

# Admin only dependency
get_admin_user = require_role(UserRole.ADMIN)

# Teacher or Admin dependency
get_teacher_or_admin = require_any_role([UserRole.TEACHER, UserRole.ADMIN])

# Student dependency (any authenticated user can be student)
get_student_user = require_role(UserRole.STUDENT)