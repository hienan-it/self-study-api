"""
app/core/responses.py

Helpers to build the unified success response shape required by api-design.md:

Single resource:
    { "success": true, "data": { ... } }

Paginated list:
    { "success": true, "data": { "content": [...], "page": 0, "size": 20,
                                  "totalElements": 143, "totalPages": 8 } }
"""

from typing import Any


def success_response(data: Any) -> dict:
    """Wrap any serialisable object in the standard success envelope."""
    return {"success": True, "data": data}


def paginated_response(
    *,
    content: list,
    page: int,
    size: int,
    total_elements: int,
    total_pages: int,
) -> dict:
    """
    Build a paginated success response.

    Note: field names are snake_case here; the frontend receives camelCase
    because Pydantic's alias_generator handles serialisation at the schema layer.
    For plain dicts returned directly we use the camelCase keys expected by the
    api-design.md spec.
    """
    return {
        "success": True,
        "data": {
            "content": content,
            "page": page,
            "size": size,
            "totalElements": total_elements,
            "totalPages": total_pages,
        },
    }
