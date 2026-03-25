from app.db.base import Base
from app.db.mixins.auditable_mixin import AuditableMixin
from app.db.mixins.soft_delete_mixin import SoftDeleteMixin


class BaseModel(Base, AuditableMixin, SoftDeleteMixin):
    __abstract__ = True
    USER_TABLE = "users"
