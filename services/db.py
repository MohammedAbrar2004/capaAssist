"""DB factory — hands out the `CapaRepository` implementation selected by
`config.DB_BACKEND`. Agents/retrieval call `get_repository()`; they never
import `repositories.postgres` (or, later, `repositories.oracle`) directly.
"""

from psycopg2.pool import ThreadedConnectionPool

import config
from repositories.base import CapaRepository
from repositories.postgres import PostgresCapaRepository

_pool: ThreadedConnectionPool | None = None
_repository: CapaRepository | None = None


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(
            config.DB_POOL_MIN, config.DB_POOL_MAX, config.DATABASE_URL
        )
    return _pool


def get_repository() -> CapaRepository:
    global _repository
    if _repository is not None:
        return _repository

    if config.DB_BACKEND == "postgres":
        _repository = PostgresCapaRepository(_get_pool())
    else:
        raise ValueError(f"Unknown DB_BACKEND: {config.DB_BACKEND!r}")

    return _repository
