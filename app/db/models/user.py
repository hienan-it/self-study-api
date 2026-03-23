from sqlalchemy import Column, Integer, String
import enum

from app.db.models.base_model import BaseModel
from app.utils.enum_as_string import EnumAsString


class UserRole(str, enum.Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


class User(BaseModel):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(EnumAsString(UserRole), default=UserRole.STUDENT, nullable=False)

    def has_role(self, role: UserRole) -> bool:
        return self.role == role

    def has_any_role(self, roles: list[UserRole]) -> bool:
        return self.role in roles

    def has_all_roles(self, roles: list[UserRole]) -> bool:
        # For single role per user, this checks if user's role is in the list
        return self.role in roles