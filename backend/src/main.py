import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routers import chat, documents, health, jobs
from src.core.constants import APP_NAME
from src.core.errors import AppError
from src.core.logging import setup_logging
from src.lifespan import lifespan

setup_logging()
logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title=APP_NAME, version="0.1.0", lifespan=lifespan)

    # <--- NEW: Add CORS Middleware --->
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.error("application_error", code=exc.code, message=exc.message, path=request.url.path)
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "details": exc.details},
        )

    # Include Routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(documents.router, prefix="/documents", tags=["Documents"])
    app.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
    app.include_router(chat.router, prefix="/chat", tags=["Chat"])

    return app


app = create_app()
