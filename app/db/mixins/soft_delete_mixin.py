from sqlalchemy import Column, Boolean

class SoftDeleteMixin:
    is_deleted = Column(Boolean, default=False)
