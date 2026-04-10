from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api.routes import auth, users, lessons, modules, subjects, knowledge, sessions
from app.api.routes.ai import router as ai_router
from app.db.session import SessionLocal
from app.utils.setup_admin import create_initial_admin
from app.core.exceptions import register_exception_handlers
from app.core.middleware import LoggingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler for startup and shutdown logic

    Startup:
    - Creates initial admin user if not exists

    Shutdown:
    - Clean up resources (if needed)
    """
    from app.core.logger import access_logger, error_logger
    
    # ============================================
    # STARTUP LOGIC
    # ============================================
    # Run migrations automatically
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        access_logger.info("Database migrations applied successfully", extra={"action_code": "STARTUP"})
    except Exception as e:
        error_logger.error(f"Failed to apply database migrations: {e}", extra={"action_code": "STARTUP"})
        raise

    access_logger.info("Starting Study Master API...", extra={"action_code": "STARTUP"})

    # Create initial admin user
    db = SessionLocal()
    try:
        create_initial_admin(db)
    except Exception as e:
        error_logger.error(f"Error during startup: {e}", extra={"action_code": "STARTUP"})
        # Don't raise - let the app start anyway
    finally:
        db.close()

    access_logger.info("App started", extra={"action_code": "STARTUP"})
    access_logger.info("Application startup complete!", extra={"action_code": "STARTUP"})

    yield

    # ============================================
    # SHUTDOWN LOGIC
    # ============================================
    access_logger.info("Shutting down Study Master API...", extra={"action_code": "SHUTDOWN"})

# ============================================
# FASTAPI APPLICATION
# ============================================

app = FastAPI(
    title="Study Master API",
    description="API for Study Master platform with AI-powered features",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    redirect_slashes=False
)

register_exception_handlers(app)

# ============================================
# MIDDLEWARE
# ============================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://self-study-user-ui.vercel.app", "*",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(LoggingMiddleware)

# ============================================
# ROUTERS
# ============================================

app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(lessons.router, prefix="/api/v1")
app.include_router(modules.router, prefix="/api/v1")
app.include_router(subjects.router, prefix="/api/v1")
app.include_router(knowledge.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")


# ============================================
# ROOT ENDPOINTS
# ============================================


@app.get("/")
def read_root():
    """Root endpoint - API information"""
    return {
        "message": "Study Master API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Study Master API",
        "version": "1.0.0",
    }


# ============================================
# DEVELOPMENT SERVER
# ============================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info"
    )
