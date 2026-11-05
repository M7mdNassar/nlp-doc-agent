import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.core.constants import APP_NAME
from src.core.errors import AppError
from src.core.logging import setup_logging
from src.lifespan import lifespan

# Setup logging before anything else
setup_logging()
logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title=APP_NAME,
        version="0.1.0",
        lifespan=lifespan,
    )

    # Global Exception Handler for our custom AppErrors
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.error("application_error", code=exc.code, message=exc.message, path=request.url.path)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )

    # Root Endpoint
    @app.get("/")
    async def root() -> dict[str, str]:
        return {"message": f"Welcome to {APP_NAME} API"}

    return app


app = create_app()
