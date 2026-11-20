from groq import APIConnectionError, APIStatusError, AsyncGroq

from src.core.config import settings
from src.core.errors import AppError, ValidationError

MAX_AUDIO_BYTES = 10 * 1024 * 1024
AUDIO_EXTENSIONS = {"wav", "webm", "ogg", "mp3", "m4a", "mp4", "flac"}


async def transcribe_audio(content: bytes, extension: str) -> str:
    if not settings.GROQ_API_KEY.strip():
        raise AppError("TRANSCRIPTION_UNAVAILABLE", "Voice queries require a Groq API key.", 503)
    try:
        async with AsyncGroq(api_key=settings.GROQ_API_KEY, timeout=30, max_retries=0) as client:
            result = await client.audio.transcriptions.create(
                file=(f"query.{extension}", content),
                model=settings.TRANSCRIPTION_MODEL,
                response_format="json",
                temperature=0,
            )
    except APIStatusError as exc:
        if exc.status_code in {400, 413, 415, 422}:
            raise ValidationError("The audio could not be read. Record a new clip.") from exc
        if exc.status_code == 429:
            raise AppError(
                "TRANSCRIPTION_RATE_LIMITED", "Voice transcription is rate limited.", 429
            ) from exc
        raise AppError(
            "TRANSCRIPTION_UNAVAILABLE", "Voice transcription is unavailable.", 503
        ) from exc
    except APIConnectionError as exc:
        raise AppError(
            "TRANSCRIPTION_UNAVAILABLE", "Could not reach voice transcription.", 503
        ) from exc

    text = result.text.strip()
    if not text:
        raise ValidationError("No speech was recognized. Try recording again.")
    if len(text) > 8000:
        raise ValidationError("The transcript is too long. Record a shorter question.")
    return text
