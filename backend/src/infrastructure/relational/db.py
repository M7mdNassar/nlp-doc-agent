from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event
from src.core.config import settings

# Create async engine
# For SQLite, we use aiosqlite. We configure it for WAL (Write-Ahead Logging)
# to allow concurrent reads while writing.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)

# Enable WAL mode and foreign keys for SQLite
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record): # type: ignore
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

async def get_db_session() -> AsyncSession: # type: ignore
    """Dependency for FastAPI routes or use cases."""
    async with AsyncSessionLocal() as session:
        yield session