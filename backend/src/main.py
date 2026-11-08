import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.routers.chat import router as chat_router
from src.api.routers.documents import router as documents_router
from src.api.routers.health import router as health_router
from src.api.routers.jobs import router as jobs_router
from src.core.constants import APP_NAME
from src.core.errors import AppError
from src.core.logging import setup_logging
from src.lifespan import lifespan

setup_logging()
logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title=APP_NAME, version="0.1.0", lifespan=lifespan)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.error("application_error", code=exc.code, message=exc.message, path=request.url.path)
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "details": exc.details},
        )

    # Include Routers
    app.include_router(health_router, tags=["Health"])
    app.include_router(documents_router, prefix="/documents", tags=["Documents"])
    app.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
    app.include_router(chat_router, prefix="/chat", tags=["Chat"])

    return app


app = create_app()
