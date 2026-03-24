"""
app/core/exceptions.py

Centralized exception definitions and handlers for the Educational Platform API.

All handlers produce the unified error shape required by api-design.md:
{
    "success": false,
    "code":    "RESOURCE_NOT_FOUND",
    "message": "...",
    "timestamp": "<ISO-8601 UTC>",
    "path":    "/api/v1/..."
}
"""
import traceback
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


# ============================================
# DOMAIN EXCEPTIONS
# ============================================

class AppException(Exception):
    """Base class for all application-level exceptions."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ResourceNotFoundException(AppException):
    """Raised when a requested resource does not exist."""

    def __init__(self, resource: str, resource_id: int | str) -> None:
        super().__init__(
            code="RESOURCE_NOT_FOUND",
            message=f"{resource} with id {resource_id} not found",
            status_code=404,
        )


class DuplicateResourceException(AppException):
    """Raised when a unique-constraint is violated."""

    def __init__(self, resource: str, field: str, value: str) -> None:
        super().__init__(
            code="DUPLICATE_RESOURCE",
            message=f"{resource} with {field} '{value}' already exists",
            status_code=409,
        )


class BusinessRuleException(AppException):
    """Raised when a business rule is violated (422)."""

    def __init__(self, message: str) -> None:
        super().__init__(
            code="BUSINESS_RULE_VIOLATED",
            message=message,
            status_code=422,
        )


class ForbiddenException(AppException):
    """Raised when an authenticated user lacks permission."""

    def __init__(self, message: str = "You do not have permission to perform this action") -> None:
        super().__init__(
            code="FORBIDDEN",
            message=message,
            status_code=403,
        )


# ============================================
# SHARED HELPER
# ============================================

def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _error_body(code: str, message: str, path: str) -> dict:
    return {
        "success": False,
        "code": code,
        "message": message,
        "timestamp": _now_iso(),
        "path": path,
    }


# ============================================
# HTTP STATUS CODE → ERROR CODE MAPPING
# ============================================

_STATUS_TO_CODE: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "RESOURCE_NOT_FOUND",
    409: "DUPLICATE_RESOURCE",
    422: "BUSINESS_RULE_VIOLATED",
    500: "INTERNAL_ERROR",
}


# ============================================
# EXCEPTION HANDLERS
# ============================================

async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message, str(request.url.path)),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = _STATUS_TO_CODE.get(exc.status_code, "INTERNAL_ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(code, str(exc.detail), str(request.url.path)),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {"field": ".".join(str(loc) for loc in e["loc"] if loc != "body"), "message": e["msg"]}
        for e in exc.errors()
    ]
    body = _error_body("VALIDATION_FAILED", "Request validation failed", str(request.url.path))
    body["errors"] = errors  # type: ignore[assignment]
    return JSONResponse(status_code=422, content=body)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    print("🔥 UNHANDLED ERROR:", repr(exc))
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content=_error_body("INTERNAL_ERROR", "An unexpected error occurred", str(request.url.path)),
    )


# ============================================
# REGISTRATION HELPER
# ============================================

def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI app instance."""
    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)  # type: ignore[arg-type]
