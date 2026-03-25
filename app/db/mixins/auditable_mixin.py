from sqlalchemy import Column, Integer, ForeignKey, DateTime, func
from sqlalchemy.orm import declared_attr

class AuditableMixin:
    USER_TABLE = "users"

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    @declared_attr
    def created_by(self):
        return Column(Integer, ForeignKey(f"{self.USER_TABLE}.id"), nullable=True)

    @declared_attr
    def updated_by(self):
        return Column(Integer, ForeignKey(f"{self.USER_TABLE}.id"), nullable=True)
