from typing import Generic, List, TypeVar
from pydantic import BaseModel
from pydantic.generics import GenericModel

from app.schemas.mixins.auditable import AuditableSchema
from app.schemas.mixins.soft_delete import SoftDeletableSchema


def to_camel(string: str) -> str:
    parts = string.split('_')
    return parts[0] + ''.join(word.capitalize() for word in parts[1:])


class APIModel(BaseModel):
    class Config:
        alias_generator = to_camel
        populate_by_name = True
        from_attributes = True


T = TypeVar("T")

class Page(GenericModel, Generic[T]):
    data: List[T]
    page: int
    page_size: int
    total: int
    total_pages: int