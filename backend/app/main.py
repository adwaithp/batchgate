"""FastAPI application factory and router wiring."""

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import audit, auth, batches, dashboard, knowledge, orders, specs
from app.core.config import get_settings
from app.core.database import check_schema
from app.services.batches import WorkflowError


def create_app() -> FastAPI:
    """Build the API application; refuses to start on an outdated schema."""
    settings = get_settings()
    check_schema()
    app = FastAPI(
        title="BatchGate API",
        description="AI quality gate for specialty chemical batches.",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(WorkflowError)
    async def workflow_error(_: Request, exc: WorkflowError) -> JSONResponse:
        """Return a business-rule violation as a JSON error."""
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["meta"])
    def health() -> dict:
        """Report that the API is up."""
        return {"status": "ok"}

    api.include_router(auth.router)
    api.include_router(dashboard.router)
    api.include_router(batches.router)
    api.include_router(orders.router)
    api.include_router(specs.router)
    api.include_router(audit.router)
    api.include_router(knowledge.router)
    app.include_router(api)
    return app


app = create_app()
