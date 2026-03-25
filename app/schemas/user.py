from datetime import datetime
from typing import Optional

from pydantic import EmailStr

from app.schemas.base import APIModel
from app.schemas.mixins.auditable import AuditableSchema
from app.db.models.user import UserRole
from app.schemas.mixins.soft_delete import SoftDeletableSchema


class UserBase(APIModel):
    username: str
    email: EmailStr
    role: UserRole = UserRole.STUDENT


class UserCreate(UserBase):
    password: str


class UserUpdate(APIModel, SoftDeletableSchema):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None


class UserResponse(UserBase, AuditableSchema, SoftDeletableSchema):
    id: int
    is_active: bool


class LoginRequest(APIModel):
    username: str
    password: str


class Token(APIModel):
    access_token: str
    token_type: str


class TokenData(APIModel):
    username: Optional[str] = None