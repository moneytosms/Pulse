"""@stub decorator: route returns fixture data and marks the response X-Pulse-Stub: true."""

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

# Module-level inventory for a future CI "stub count" check.
STUB_ROUTES: list[str] = []


def stub(fixture: Any) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Decorate a route handler to return `fixture` unconditionally, tagged as a stub."""

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        STUB_ROUTES.append(f"{func.__module__}.{func.__qualname__}")

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            response = kwargs.get("response")
            if response is not None:
                response.headers["X-Pulse-Stub"] = "true"
            return fixture

        return wrapper

    return decorator
