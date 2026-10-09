"""An outer business operation owns the transaction, including audit and in-app delivery."""

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Concatenate

from sqlalchemy.ext.asyncio import AsyncSession


def transactional[**P, T](
    operation: Callable[Concatenate[AsyncSession, P], Awaitable[T]],
) -> Callable[Concatenate[AsyncSession, P], Awaitable[T]]:
    @wraps(operation)
    async def run(session: AsyncSession, /, *args: P.args, **kwargs: P.kwargs) -> T:
        try:
            result = await operation(session, *args, **kwargs)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise

    return run
