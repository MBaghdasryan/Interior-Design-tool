import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import get_settings
from .db import Base, SessionLocal, engine
from .errors import http_error_handler, validation_error_handler
from .jobs import catalog as catalog_jobs  # noqa: F401  (register job handlers)
from .jobs import documents, pipeline, recognize  # noqa: F401
from .routers import admin, auth, catalog, commerce, partners, projects
from .routers import documents as documents_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()

app = FastAPI(title=f"{settings.brand_name} API", version="0.1.0", description="AI interior design & real-product sourcing platform",
              openapi_url="/api/v1/openapi.json", docs_url="/api/docs")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, projects.router, commerce.router, documents_router.router, catalog.router, admin.router, partners.router):
    app.include_router(r)


app.add_exception_handler(HTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)


@app.exception_handler(ValueError)
async def value_error(_: Request, exc: ValueError):
    return JSONResponse(status_code=422, content={"code": "validation", "params": {"info": str(exc)[:300]}, "detail": str(exc)})


WEAK_SECRETS = {"dev-only-change-me", "change-me-to-a-long-random-string", "test-secret", ""}


def production_guard(s=settings) -> None:
    """Refuse to start a production instance with unsafe settings (template secret, demo data, insecure cookies)."""
    if not s.is_production:
        return
    problems = []
    if s.secret_key in WEAK_SECRETS or len(s.secret_key) < 32:
        problems.append("SECRET_KEY is a template or shorter than 32 characters")
    if s.seed_demo:
        problems.append("SEED_DEMO must be false")
    if not s.cookie_secure:
        problems.append("COOKIE_SECURE must be true")
    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


@app.on_event("startup")
def startup() -> None:
    production_guard()
    # Development convenience: create tables if migrations were not run. Production
    # runs `alembic upgrade head` in the container entrypoint (see Dockerfile/compose).
    # Schema is managed by Alembic (`python -m app.migrate`, also run by the container
    # entrypoint). Throw-away test databases use create_all.
    if settings.env == "test":
        Base.metadata.create_all(engine)
    else:
        from .migrate import main as migrate

        migrate()
    if settings.seed_demo:
        from .seed import seed

        with SessionLocal() as db:
            seed(db)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/ready")
def ready():
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ready", "brand": settings.brand_name, "aps": settings.aps_enabled}


@app.get("/api/v1/config")
def public_config():
    """Non-secret runtime config for the web client."""
    from .ai.orchestrator import get_orchestrator

    return {"brand_name": settings.brand_name, "brand_tagline": settings.brand_tagline, "currency": settings.base_currency,
            "aps_enabled": settings.aps_enabled, "external_catalog_enabled": settings.external_catalog_enabled,
            "external_fetch_live": settings.external_fetch_live,
            "ai": {k: v["available"] for k, v in get_orchestrator().status().items()}}
