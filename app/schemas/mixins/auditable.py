from datetime import datetime
from typing import Optional

class AuditableSchema:
    created_at: Optional[datetime]
    created_by: Optional[int]
    updated_at: Optional[datetime]
    updated_by: Optional[int]