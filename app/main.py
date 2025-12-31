import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import AsyncSessionLocal
from app.api.v1 import auth as auth_routes
from app.api.v1 import health as health_routes
from app.api.v1 import masters as masters_routes
from app.api.v1 import companies as companies_routes
from app.api.v1 import jobs as jobs_routes
from app.api.v1 import candidates as candidates_routes
from app.api.v1 import candidate_payments as candidate_payments_routes
from app.api.v1 import public as public_routes
from app.api.v1 import interviews as interviews_routes
from app.api.v1 import placement_incomes as placement_incomes_routes
from app.api.v1 import files as files_routes
from app.api.v1 import reports as reports_routes
from app.api.v1 import payments as payments_routes
from app.crud.user import get_user_by_email, create_user
from app.models.user import UserRole
from app.schemas.user import UserCreate


setup_logging()

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin).rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS],
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (serve uploaded media)
app.mount(
    "/media",
    StaticFiles(directory=settings.MEDIA_ROOT, check_dir=True),
    name="media",
)


@app.on_event("startup")
async def init_initial_superuser() -> None:
    """Create an initial admin user if none exists and settings are provided."""
    if not settings.FIRST_SUPERUSER_EMAIL or not settings.FIRST_SUPERUSER_PASSWORD:
        logger.info("Initial superuser bootstrap skipped")
        return

    async with AsyncSessionLocal() as session:
        existing = await get_user_by_email(session, settings.FIRST_SUPERUSER_EMAIL)
        if existing:
            logger.info("Initial superuser already exists")
            return

        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER_EMAIL,
            full_name=settings.FIRST_SUPERUSER_FULL_NAME or "Admin User",
            password=settings.FIRST_SUPERUSER_PASSWORD,
            role=UserRole.admin.value,
        )
        logger.info("Creating initial superuser")
        await create_user(session, user_in)

# Routers
app.include_router(health_routes.router, prefix=settings.API_V1_STR)
app.include_router(auth_routes.router, prefix=settings.API_V1_STR)
app.include_router(public_routes.router, prefix=settings.API_V1_STR)
app.include_router(masters_routes.router, prefix=settings.API_V1_STR)
app.include_router(companies_routes.router, prefix=settings.API_V1_STR)
app.include_router(jobs_routes.router, prefix=settings.API_V1_STR)
app.include_router(candidates_routes.router, prefix=settings.API_V1_STR)
app.include_router(candidate_payments_routes.router, prefix=settings.API_V1_STR)
app.include_router(interviews_routes.router, prefix=settings.API_V1_STR)
app.include_router(placement_incomes_routes.router, prefix=settings.API_V1_STR)
app.include_router(files_routes.router, prefix=settings.API_V1_STR)
app.include_router(reports_routes.router, prefix=settings.API_V1_STR)
app.include_router(payments_routes.router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["health"])
async def root_health_check() -> dict[str, str]:
    return {"status": "ok"}
