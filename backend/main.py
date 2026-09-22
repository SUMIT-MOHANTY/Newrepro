"""
DSuite BRD Analyzer - Application Entrypoint
Lean, production-grade FastAPI application assembly and lifecycle management.
Enterprise 8-Layer Clean Architecture (< 200 lines).
"""

import os
from dotenv import load_dotenv
load_dotenv()

# Injects clean architecture layers into sys.path
import app

# Disable Hugging Face symlinks on Windows to prevent WinError 1314 permission crash
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

import asyncio
import logging
import warnings
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Silence Pydantic warnings about protected namespaces from third-party libraries
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message='.*protected namespace "model_".*',
)

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.middleware import activity_logging_middleware
from app.routers import api_router
from database import engine
import models
from scripts.run_all_migrations import run_migrations

from tokenops.api.superadmin import tokenops_admin_router, tokenops_superadmin_alias
from tokenops.api.orgadmin import tokenops_org_router
from tokenops.api.user import tokenops_user_router

# Configure logging with date and time
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# Suppress frequent polling logs in uvicorn access logs
class PollingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "/api/agent/tasks-list/" in msg or "/status?project_token=" in msg:
            return False
        return True


logging.getLogger("uvicorn.access").addFilter(PollingFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager for startup migrations, worker orchestration,
    and graceful shutdown.
    """
    logger.info("[Lifespan] Starting DSuite BRD Analyzer application...")

    # 1. Ensure database schema and run automated migrations
    try:
        models.Base.metadata.create_all(bind=engine)
        run_migrations(verbose=False)
        logger.info("[Lifespan] Database schemas verified and migrations applied.")
    except Exception as e:
        logger.error(f"[Lifespan] Startup migration error: {e}")

    # 2. Initialize asynchronous workers
    from app.workers.analysis_job_manager import (
        initialize_job_manager,
        shutdown_job_manager,
    )
    from app.workers.capture_agent_logs import auto_capture_loop
    from app.workers.daily_billing_email_service import (
        daily_billing_email_scheduler,
    )

    await initialize_job_manager()
    log_task = asyncio.create_task(auto_capture_loop())
    billing_email_task = asyncio.create_task(daily_billing_email_scheduler())
    logger.info("[Lifespan] Background job manager and schedulers active.")

    yield

    # 3. Graceful shutdown of background workers
    logger.info("[Lifespan] Initiating graceful shutdown...")
    log_task.cancel()
    billing_email_task.cancel()
    try:
        await asyncio.gather(log_task, billing_email_task, return_exceptions=True)
    except Exception:
        pass
    await shutdown_job_manager()
    logger.info("[Lifespan] Shutdown completed successfully.")


app = FastAPI(
    title="DSuite BRD Analyzer API",
    version="2.0.0",
    description="Enterprise Multi-Agent Requirements, Governance, and Orchestration API",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Centralized Exception Handlers
register_exception_handlers(app)

# Register Activity Logging & Context Tracking Middleware
app.middleware("http")(activity_logging_middleware)

# Mount Clean Architecture Domain Routers (Dual Routing: /api prefix and root /)
app.include_router(api_router, prefix="/api")
app.include_router(api_router)

# Mount TokenOps Domain Routers
app.include_router(tokenops_admin_router)
app.include_router(tokenops_superadmin_alias)
app.include_router(tokenops_org_router)
app.include_router(tokenops_user_router)

# Mount Static File Upload Directory
uploads_path = Path("uploads")
uploads_path.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/", tags=["Health"])
@app.get("/health", tags=["Health"])
def health_check():
    """System health check and architectural status probe."""
    return {
        "status": "healthy",
        "service": "DSuite BRD Analyzer API",
        "version": "2.0.0",
        "architecture": "8-Layer Clean Architecture",
    }