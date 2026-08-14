"""
analytics.py — Day 8 call analytics writer for DeutschMate.

Writes one row per call to call_analytics using the existing asyncpg
pool from db.py.  Never stores transcript content.
"""

import logging
import uuid

import asyncpg
from db import get_pool, reset_pool

logger = logging.getLogger("agent.analytics")


async def record_call(
    session_id: str,
    learner_id: str,
    channel: str,
    outcome: str,
) -> None:
    """
    Insert a single analytics row using an isolated pool connection.
    Silently swallows errors so a DB outage never crashes the agent.

    Args:
        session_id: Unique ID for this call (uuid or room name).
        learner_id: Google sub / room-name fallback.
        channel:    "browser" or "sip".
        outcome:    "success" or "failed".
    """
    query = """
        INSERT INTO call_analytics (session_id, learner_id, channel, outcome)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (session_id) DO UPDATE
            SET outcome    = EXCLUDED.outcome,
                learner_id = EXCLUDED.learner_id;
    """

    for attempt in range(2):
        pool = await get_pool()
        if pool is None:
            logger.warning("[ANALYTICS] Pool unavailable — analytics row NOT written.")
            return

        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    query,
                    session_id,
                    learner_id,
                    channel,
                    outcome,
                )
            logger.info(
                "[ANALYTICS] Recorded: session=%s learner=%s channel=%s outcome=%s",
                session_id,
                learner_id,
                channel,
                outcome,
            )
            return
        except (asyncpg.ConnectionDoesNotExistError, asyncpg.InterfaceError, asyncpg.InternalClientError) as exc:
            logger.warning(
                "[ANALYTICS] Connection error on attempt %d [%s]: %s — resetting pool",
                attempt + 1,
                type(exc).__name__,
                exc,
            )
            reset_pool()
        except Exception as exc:
            logger.error("[ANALYTICS] Failed to write analytics row [%s]: %s", type(exc).__name__, exc)
            reset_pool()
            return

