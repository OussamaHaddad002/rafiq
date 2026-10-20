from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.db import engine
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.llm import get_provider
from app.routes import chat, health


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_provider()  # fail fast on a missing API key instead of on the first chat request
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Rafiq API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    return app


app = create_app()
