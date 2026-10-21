from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def get_clock() -> Clock:
    """Injected so tests can pin "now" (availability and expiry depend on it)."""
    return utc_now


ClockDep = Annotated[Clock, Depends(get_clock)]
