from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.user import UserResponse
from app.api.deps import get_current_active_user
from app.core.decorators import has_any_role, has_role, is_authenticated

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
@is_authenticated()
async def read_current_user(current_user: User = Depends(get_current_active_user)):
    return current_user


@router.get("/", response_model=List[UserResponse])
@has_any_role([UserRole.ADMIN, UserRole.TEACHER])
async def list_users(
        skip: int = 0,
        limit: int = 100,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    users = db.query(User).offset(skip).limit(limit).all()
    return users


@router.get("/{user_id}", response_model=UserResponse)
@has_any_role([UserRole.ADMIN, UserRole.TEACHER])
async def get_user(
        user_id: int,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
@has_role(UserRole.ADMIN)
async def delete_user(
        user_id: int,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself"
        )

    db.delete(user)
    db.commit()
    return None