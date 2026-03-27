from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional, List
from fastapi import HTTPException, status, Depends
from app.db.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import get_password_hash, verify_password
from app.db.session import get_db


class UserService:
    """Service layer for user-related business logic"""

    def __init__(self, db: Session):
        self.db = db

    # ============================================
    # READ OPERATIONS
    # ============================================

    def get_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        return self.db.query(User).filter(User.id == user_id).first()

    def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        return self.db.query(User).filter(User.username == username).first()

    def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        return self.db.query(User).filter(User.email == email).first()

    def page(
            self,
            page: int = 1,
            page_size: int = 10,
            sort_by: str = None,
            sort_order: str = None,
            role: Optional[UserRole] = None,
            is_deleted: Optional[bool] = None,
            search: Optional[str] = None
    ) -> List[User]:
        """
        Get all users with optional filters

        Args:
            page:
            page_size:
            sort_by:
            sort_order:
            role: Filter by user role
            is_deleted: Filter by active status
            search: Search in username and email

        Returns:
            Page of users matching the criteria
        """
        query = self.db.query(User)

        # Apply filters
        if role is not None:
            query = query.filter(User.role == role)

        if is_deleted is not None:
            query = query.filter(User.is_deleted == is_deleted)

        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    User.username.ilike(search_pattern),
                    User.email.ilike(search_pattern)
                ))

        total = query.count()

        # Calculate offset
        offset = (page - 1) * page_size

        users = (
            query.order_by(User.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

        return {
            "data": users,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size
        }

    def get_all(
            self,
            skip: int = 0,
            limit: int = 100,
            role: Optional[UserRole] = None,
            is_deleted: Optional[bool] = None,
            search: Optional[str] = None
    ) -> List[User]:
        """
        Get all users with optional filters

        Args:
            skip: Number of records to skip (pagination)
            limit: Maximum number of records to return
            role: Filter by user role
            is_deleted: Filter by active status
            search: Search in username and email

        Returns:
            List of users matching the criteria
        """
        query = self.db.query(User)

        # Apply filters
        if role is not None:
            query = query.filter(User.role == role)

        if is_deleted is not None:
            query = query.filter(User.is_deleted == is_deleted)

        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    User.username.ilike(search_pattern),
                    User.email.ilike(search_pattern)
                )
            )

        # Order by creation date (newest first) and apply pagination
        return query.order_by(User.created_at.desc()).offset(skip).limit(limit).all()

    def count_users(
            self,
            role: Optional[UserRole] = None,
            is_deleted: Optional[bool] = None
    ) -> dict:
        """
        Get user count statistics

        Args:
            role: Filter by role
            is_deleted: Filter by active status

        Returns:
            Dictionary with total count and breakdown by role
        """
        query = self.db.query(User)

        if role is not None:
            query = query.filter(User.role == role)

        if is_deleted is not None:
            query = query.filter(User.is_deleted == is_deleted)

        total = query.count()

        return {
            "total": total,
            "by_role": {
                "students": self.db.query(User).filter(User.role == UserRole.STUDENT).count(),
                "teachers": self.db.query(User).filter(User.role == UserRole.TEACHER).count(),
                "admins": self.db.query(User).filter(User.role == UserRole.ADMIN).count(),
            },
            "by_status": {
                "active": self.db.query(User).filter(User.is_deleted == False).count(),
                "inactive": self.db.query(User).filter(User.is_deleted == True).count(),
            }
        }

    def exists_by_username(self, username: str, exclude_id: Optional[int] = None) -> bool:
        """
        Check if username exists

        Args:
            username: Username to check
            exclude_id: Exclude this user ID from check (for updates)

        Returns:
            True if username exists, False otherwise
        """
        query = self.db.query(User).filter(User.username == username)
        if exclude_id:
            query = query.filter(User.id != exclude_id)
        return query.first() is not None

    def exists_by_email(self, email: str, exclude_id: Optional[int] = None) -> bool:
        """
        Check if email exists

        Args:
            email: Email to check
            exclude_id: Exclude this user ID from check (for updates)

        Returns:
            True if email exists, False otherwise
        """
        query = self.db.query(User).filter(User.email == email)
        if exclude_id:
            query = query.filter(User.id != exclude_id)
        return query.first() is not None

    # ============================================
    # CREATE OPERATIONS
    # ============================================

    def create(self, user_data: UserCreate) -> User:
        """
        Create a new user

        Args:
            user_data: User creation data

        Returns:
            Created user

        Raises:
            HTTPException: If username or email already exists
        """
        # Check if username exists
        if self.exists_by_username(user_data.username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered"
            )

        # Check if email exists
        if self.exists_by_email(user_data.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Create user
        user = User(
            username=user_data.username,
            email=user_data.email,
            hashed_password=get_password_hash(user_data.password),
            role=user_data.role,
            is_deleted=False
        )

        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        return user

    def create_admin(self, username: str, email: str, password: str) -> User:
        """
        Create an admin user

        Args:
            username: Admin username
            email: Admin email
            password: Admin password

        Returns:
            Created admin user
        """
        # Check if admin already exists
        if self.exists_by_username(username):
            return self.get_by_username(username)

        user = User(
            username=username,
            email=email,
            hashed_password=get_password_hash(password),
            role=UserRole.ADMIN,
            is_deleted=False
        )

        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        return user

    # ============================================
    # UPDATE OPERATIONS
    # ============================================

    def update(self, user_id: int, user_data: UserUpdate) -> User:
        """
        Update user

        Args:
            user_id: User ID to update
            user_data: Update data

        Returns:
            Updated user

        Raises:
            HTTPException: If user not found or validation fails
        """
        user = self.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id {user_id} not found"
            )

        # Get only fields that were actually provided
        update_data = user_data.model_dump(exclude_unset=True)

        # Check username uniqueness
        if "username" in update_data:
            if self.exists_by_username(update_data["username"], exclude_id=user_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already taken"
                )

        # Check email uniqueness
        if "email" in update_data:
            if self.exists_by_email(update_data["email"], exclude_id=user_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already taken"
                )

        # Update user fields
        for field, value in update_data.items():
            setattr(user, field, value)

        self.db.commit()
        self.db.refresh(user)

        return user

    def update_password(self, user_id: int, new_password: str) -> User:
        """
        Update user password

        Args:
            user_id: User ID
            new_password: New password (plain text)

        Returns:
            Updated user

        Raises:
            HTTPException: If user not found
        """
        user = self.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id {user_id} not found"
            )

        user.hashed_password = get_password_hash(new_password)
        self.db.commit()
        self.db.refresh(user)

        return user

    def deactivate(self, user_id: int, current_user_id: int) -> User:
        """
        Deactivate user (soft delete)

        Args:
            user_id: User ID to deactivate
            current_user_id: ID of user performing the action

        Returns:
            Deactivated user

        Raises:
            HTTPException: If user not found or trying to deactivate self
        """
        user = self.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id {user_id} not found"
            )

        # Prevent self-deactivation
        if user_id == current_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate yourself"
            )

        user.is_deleted = True
        self.db.commit()
        self.db.refresh(user)

        return user

    def activate(self, user_id: int) -> User:
        """
        Activate a deactivated user

        Args:
            user_id: User ID to activate

        Returns:
            Activated user

        Raises:
            HTTPException: If user not found
        """
        user = self.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id {user_id} not found"
            )

        user.is_deleted = False
        self.db.commit()
        self.db.refresh(user)

        return user

    # ============================================
    # DELETE OPERATIONS
    # ============================================

    def delete(self, user_id: int, current_user_id: int) -> None:
        """
        Delete user (hard delete)

        Args:
            user_id: User ID to delete
            current_user_id: ID of user performing the action

        Raises:
            HTTPException: If user not found, trying to delete self, or deleting last admin
        """
        user = self.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id {user_id} not found"
            )

        # Prevent self-deletion
        if user_id == current_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete yourself"
            )

        # Prevent deletion of last admin
        if user.role == UserRole.ADMIN:
            admin_count = self.db.query(User).filter(User.role == UserRole.ADMIN).count()
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete the last admin user"
                )

        self.db.delete(user)
        self.db.commit()

    # ============================================
    # AUTHENTICATION OPERATIONS
    # ============================================

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate user with username and password

        Args:
            username: Username
            password: Plain text password

        Returns:
            User if authentication successful, None otherwise
        """
        user = self.get_by_username(username)
        if not user:
            return None

        if not verify_password(password, user.hashed_password):
            return None

        return user

    def has_role(self, user: User, role: UserRole) -> bool:
        """Check if user has specific role"""
        return user.role == role

    def has_any_role(self, user: User, roles: List[UserRole]) -> bool:
        """Check if user has any of the specified roles"""
        return user.role in roles


# ============================================
# DEPENDENCY FOR GETTING SERVICE
# ============================================

def get_user_service(db: Session = Depends(get_db)) -> UserService:
    """
    Dependency to get UserService instance

    Usage in routes:
        user_service: UserService = Depends(get_user_service)
    """
    return UserService(db)