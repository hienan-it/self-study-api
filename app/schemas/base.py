from typing import Generic, List, TypeVar
from pydantic import BaseModel, ConfigDict


def to_camel(string: str) -> str:
    parts = string.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


class APIModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


T = TypeVar("T")


class Page(APIModel, Generic[T]):
    """
    Paginated response wrapper.

    Snake_case fields are auto-converted to camelCase by APIModel's alias_generator:
      content        → "content"
      page           → "page"
      size           → "size"
      total_elements → "totalElements"
      total_pages    → "totalPages"
    """

    content: List[T]
    page: int
    size: int
    total_elements: int
    total_pages: int
