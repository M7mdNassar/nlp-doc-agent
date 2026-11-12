from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM Providers
    GROQ_API_KEY: str = Field(default="", description="Groq API Key")
    CEREBRAS_API_KEY: str = Field(default="", description="Cerebras API Key")
    OPENROUTER_API_KEY: str = Field(default="", description="OpenRouter API Key")

    # Infrastructure
    QDRANT_URL: str = Field(default="http://qdrant:6333")
    REDIS_URL: str = Field(default="redis://redis:6379/0")
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./data/app.db")

    # App Config
    JWT_SECRET: str = Field(default="super_secret_jwt_key_change_in_production")
    LOG_LEVEL: str = Field(default="info")
    DATA_DIR: str = Field(default="/app/data")
    MAX_UPLOAD_BYTES: int = Field(default=50 * 1024 * 1024, gt=0)
    LLM_MODEL: str = Field(default="openai/gpt-oss-120b")
    # Ordered JSON array in .env. Set [] to disable fallback.
    LLM_FALLBACK_MODELS: list[str] = Field(
        default_factory=lambda: [
            "openai/gpt-oss-20b",
            "qwen/qwen3.8-27b",
            "openai/gpt-oss-safeguard-20b",
        ]
    )

    # Models
    EMBEDDING_MODEL: str = Field(default="BAAI/bge-small-en-v1.5")
    RERANKER_MODEL: str = Field(default="BAAI/bge-reranker-base")
    EMBEDDING_DEVICE: str = Field(default="cpu")
    RERANKER_DEVICE: str = Field(default="cpu")
    EMBEDDING_BATCH_SIZE: int = Field(default=4, gt=0)
    RERANKER_BATCH_SIZE: int = Field(default=4, gt=0)


settings = Settings()
