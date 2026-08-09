"""
db.py — PostgreSQL connection pool for DeutschMate learner memory.

Reads DATABASE_URL from environment. Never hardcodes credentials.
The pool is lazily initialized on first use and shared across calls.
Handles loop closures and executor shutdowns automatically.
"""

import asyncio
import logging
import os
from typing import Optional

import asyncpg

logger = logging.getLogger("agent.db")

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> Optional[asyncpg.Pool]:
    """Return (and lazily create) the shared asyncpg connection pool.

    Returns None if DATABASE_URL is not configured or if the connection
    cannot be established, allowing the agent to continue without memory.
    """
    global _pool

    if _pool is not None:
        try:
            # Check if pool or underlying event loop is closed/closing
            if getattr(_pool, "_closed", False) or (_pool._loop and _pool._loop.is_closed()):
                logger.warning("[DIAGNOSTIC] Existing pool or event loop was closed — resetting pool.")
                _pool = None
        except Exception:
            _pool = None

    if _pool is not None:
        return _pool

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.warning(
            "DATABASE_URL is not set — learner memory is disabled for this session."
        )
        return None

    try:
        current_loop = asyncio.get_running_loop()
        _pool = await asyncpg.create_pool(
            dsn=database_url,
            min_size=1,
            max_size=5,
            command_timeout=10,
            loop=current_loop,
        )
        logger.info("[DIAGNOSTIC] PostgreSQL connection pool created successfully.")
        return _pool
    except Exception as exc:
        # Log error detail without exposing DSN/password
        logger.error(
            "[DIAGNOSTIC] Failed to connect to PostgreSQL [%s]: %s",
            type(exc).__name__,
            exc,
        )
        _pool = None
        return None


def reset_pool() -> None:
    """Reset the pool instance if an executor/connection error occurred."""
    global _pool
    _pool = None
    logger.info("[DIAGNOSTIC] PostgreSQL connection pool reference reset.")


async def close_pool() -> None:
    """Gracefully close the connection pool on shutdown."""
    global _pool
    if _pool is not None:
        try:
            await _pool.close()
        except Exception:
            pass
        _pool = None
        logger.info("PostgreSQL connection pool closed.")

