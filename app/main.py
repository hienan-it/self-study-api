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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler for startup and shutdown logic

    Startup:
    - Creates initial admin user if not exists

    Shutdown:
    - Clean up resources (if needed)
    """
    # ============================================
    # STARTUP LOGIC
    # ============================================
    # Run migrations automatically
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        print("✅ Database migrations applied successfully")
    except Exception:
        # logger.error(f"❌ Failed to apply database migrations: {e}")
        raise

    print("=" * 50)
    print("🚀 Starting Study Master API...")
    print("=" * 50)

    # Create initial admin user
    db = SessionLocal()
    try:
        create_initial_admin(db)
    except Exception as e:
        print(f"❌ Error during startup: {e}")
        # Don't raise - let the app start anyway
    finally:
        db.close()

    print("✅ Application startup complete!")
    print("=" * 50)

    yield

    # ============================================
    # SHUTDOWN LOGIC
    # ============================================
    print("=" * 50)
    print("🛑 Shutting down Study Master API...")
    print("=" * 50)


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
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
