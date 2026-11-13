import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.question_middleware import QuestionMiddleware
from src.api.routers.chat import router as chat_router
from src.api.routers.documents import router as documents_router
from src.api.routers.health import router as health_router
from src.api.routers.jobs import router as jobs_router
from src.core.constants import APP_NAME
from src.core.errors import AppError
from src.core.logging import setup_logging
from src.core.observability import question_details
from src.domain.exceptions.llm_provider_error import (
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
)
from src.lifespan import lifespan

setup_logging()
logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title=APP_NAME, version="0.1.0", lifespan=lifespan)
    app.add_middleware(QuestionMiddleware)

    @app.exception_handler(LLMProviderError)
    async def llm_error_handler(request: Request, exc: LLMProviderError) -> JSONResponse:
        rate_limited = isinstance(exc, LLMRateLimitError)
        code = (
            "LLM_RATE_LIMITED"
            if rate_limited
            else "LLM_CONFIGURATION_ERROR"
            if isinstance(exc, LLMConfigurationError)
            else "LLM_UNAVAILABLE"
        )
        headers = {"Cache-Control": "no-store"}
        retry_after = exc.retry_after_seconds if isinstance(exc, LLMRateLimitError) else None
        if retry_after is not None:
            headers["Retry-After"] = str(retry_after)
        logger.warning("llm_service_error", code=code, provider=exc.provider, path=request.url.path)
        return JSONResponse(
            status_code=429 if rate_limited else 503,
            headers=headers,
            content={
                "code": code,
                "message": str(exc),
                "details": {
                    **question_details(),
                    "provider": exc.provider,
                    **({"retry_after_seconds": retry_after} if retry_after is not None else {}),
                },
            },
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.warning("application_error", code=exc.code, path=request.url.path)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "details": {**exc.details, **question_details()},
            },
        )

    # Include Routers
    app.include_router(health_router, tags=["Health"])
    app.include_router(documents_router, prefix="/documents", tags=["Documents"])
    app.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
    app.include_router(chat_router, prefix="/chat", tags=["Chat"])

    return app


app = create_app()
