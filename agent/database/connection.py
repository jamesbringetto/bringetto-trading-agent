"""Database connection management."""

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from agent.config.settings import get_settings
from agent.database.models import Base


def get_engine() -> Engine:
    """Create and return a synchronous database engine."""
    settings = get_settings()
    database_url = str(settings.database_url)
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=settings.log_level == "DEBUG",
    )


def get_async_engine():
    """Create and return an async database engine."""
    settings = get_settings()
    # Convert postgresql:// to postgresql+asyncpg://
    database_url = str(settings.database_url).replace("postgresql://", "postgresql+asyncpg://")
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=settings.log_level == "DEBUG",
    )


# Session factories
_sync_session_factory: sessionmaker | None = None
_async_session_factory: async_sessionmaker | None = None


def get_sync_session_factory() -> sessionmaker:
    """Get or create the synchronous session factory."""
    global _sync_session_factory
    if _sync_session_factory is None:
        engine = get_engine()
        _sync_session_factory = sessionmaker(
            bind=engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _sync_session_factory


def get_async_session_factory() -> async_sessionmaker:
    """Get or create the async session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_async_engine()
        _async_session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _async_session_factory


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Get a synchronous database session."""
    session_factory = get_sync_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session."""
    session_factory = get_async_session_factory()
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def init_db() -> None:
    """Initialize the database by creating all tables."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


async def init_db_async() -> None:
    """Initialize the database asynchronously."""
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
