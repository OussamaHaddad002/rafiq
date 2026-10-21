import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

# Must be set before any app module reads settings.
os.environ["ENVIRONMENT"] = "test"
os.environ["LLM_PROVIDER"] = "fake"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://rafiq:rafiq@localhost:5432/rafiq_test"
)

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.db import engine
from app.main import app
from app.models import Base


@pytest.fixture(scope="session", autouse=True)
async def database() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    yield
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE messages, conversations, chunks, documents RESTART IDENTITY CASCADE")
        )
    app.dependency_overrides.clear()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@dataclass
class SSEEvent:
    event: str
    data: Any


def parse_sse(body: str) -> list[SSEEvent]:
    events: list[SSEEvent] = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        event, data_lines = "message", []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if data_lines:
            events.append(SSEEvent(event, json.loads("\n".join(data_lines))))
    return events
