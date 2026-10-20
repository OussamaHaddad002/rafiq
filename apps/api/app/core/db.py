from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


def _create_engine() -> AsyncEngine:
    settings = get_settings()
    options: dict[str, Any] = {"pool_pre_ping": True}
    if settings.environment == "test":
        # Pooled connections must not outlive the event loop that created them.
        options = {"poolclass": NullPool}
    return create_async_engine(settings.database_url, **options)


engine = _create_engine()
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
