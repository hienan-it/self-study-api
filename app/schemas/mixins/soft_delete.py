from datetime import datetime
from typing import Optional

class SoftDeletableSchema:
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[int] = None