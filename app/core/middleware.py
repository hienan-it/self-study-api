import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import logging
from app.core.logger import error_logger, access_logger

SKIP_PATHS = {"/health", "/api/health", "/api/v1/health"}
SKIP_METHODS = {"OPTIONS"}

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Don't log health checks to avoid noise
        if request.url.path in SKIP_PATHS or request.method in SKIP_METHODS:
            return await call_next(request)
            
        start_time = time.time()
        try:
            response = await call_next(request)
        except Exception as e:
            error_logger.error(
                f"Unhandled exception: {str(e)}",
                exc_info=True,
                extra={"action_code": "INTERNAL_SERVER_ERROR"}
            )
            raise

        process_time_ms = (time.time() - start_time) * 1000
        # Format: [METHOD] PATH - STATUS_CODE - LATENCYms
        if response.status_code >= 500:
            access_logger.error(
                f"[{request.method}] {request.url.path} - {response.status_code} - {process_time_ms:.2f}ms",
                extra={"action_code": "API_ACCESS"}
            )
        elif response.status_code >= 400:
            access_logger.warning(
                f"[{request.method}] {request.url.path} - {response.status_code} - {process_time_ms:.2f}ms",
                extra={"action_code": "API_ACCESS"}
            )
        else:
            access_logger.info(
                f"[{request.method}] {request.url.path} - {response.status_code} - {process_time_ms:.2f}ms",
                extra={"action_code": "API_ACCESS"}
            )
        
        return response
