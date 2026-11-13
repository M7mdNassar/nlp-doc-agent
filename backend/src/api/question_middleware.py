import structlog
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core.observability import question_scope

logger = structlog.get_logger(__name__)


class QuestionMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["path"] not in {"/chat", "/chat/stream"}
            or scope["method"] != "POST"
        ):
            await self.app(scope, receive, send)
            return
        with question_scope() as trace:
            status_code = 500
            response_started = False
            logger.info("question_started")

            async def send_with_id(message: Message) -> None:
                nonlocal status_code, response_started
                if message["type"] == "http.response.start":
                    response_started = True
                    status_code = message["status"]
                    message = {
                        **message,
                        "headers": [
                            *message.get("headers", []),
                            (b"x-question-id", trace.question_id.encode("ascii")),
                        ],
                    }
                await send(message)

            try:
                await self.app(scope, receive, send_with_id)
            except Exception as exc:
                logger.error("question_failed", error_type=type(exc).__name__)
                if response_started:
                    raise
                await JSONResponse(
                    status_code=500,
                    content={
                        "code": "INTERNAL_ERROR",
                        "message": "The question could not be processed.",
                        "details": {"question_id": trace.question_id, "usage": trace.summary()},
                    },
                )(scope, receive, send_with_id)
            finally:
                logger.info("question_completed", status_code=status_code, usage=trace.summary())
