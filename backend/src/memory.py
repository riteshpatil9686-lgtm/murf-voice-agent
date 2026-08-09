"""
memory.py — Learner memory functions for DeutschMate.

Provides:
  lookup_user(user_id)     → dict | None
  save_memory(user_id, …)  → bool

Rules enforced here:
- Never overwrites existing data with empty/None values.
- Updates last_interaction and updated_at on every save.
- Returns None / False gracefully when the database is unavailable.
- Never logs DATABASE_URL or connection strings.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from db import get_pool, reset_pool

logger = logging.getLogger("agent.memory")


async def lookup_user(user_id: str) -> Optional[dict]:
    """Search PostgreSQL for an existing learner using authenticated user_id."""
    logger.info("[DIAGNOSTIC] PostgreSQL lookup user_id: %s", user_id)
    pool = await get_pool()
    if pool is None:
        logger.warning("[DIAGNOSTIC] lookup_user: get_pool() returned None (DB unavailable).")
        return None

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT user_id, name, language_preference, german_level,
                       learning_goal, topics_covered, common_mistakes,
                       memory_consent, last_interaction, created_at, updated_at
                FROM learner_memory
                WHERE user_id = $1
                """,
                user_id,
            )

        if row is None:
            logger.info("[DIAGNOSTIC] lookup result: NOT FOUND for learner_id=%s", user_id)
            return None

        data = dict(row)
        logger.info(
            "[DIAGNOSTIC] lookup result: FOUND for learner_id=%s | memory_consent=%s",
            user_id,
            data.get("memory_consent"),
        )
        return data

    except Exception as exc:
        logger.error("[DIAGNOSTIC] lookup_user SQL error [%s]: %s", type(exc).__name__, exc)
        reset_pool()
        return None


async def update_consent(user_id: str, consent: bool) -> bool:
    """Set or update memory_consent state (TRUE or FALSE) for user_id in PostgreSQL."""
    logger.info("[DIAGNOSTIC] update_consent called for learner_id=%s | consent=%s", user_id, consent)
    pool = await get_pool()
    if pool is None:
        logger.warning("[DIAGNOSTIC] update_consent: DB unavailable.")
        return False

    now = datetime.now(timezone.utc)
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO learner_memory (user_id, memory_consent, last_interaction, created_at, updated_at)
                VALUES ($1, $2, $3, $3, $3)
                ON CONFLICT (user_id) DO UPDATE
                SET memory_consent = $2, updated_at = $3
                """,
                user_id,
                consent,
                now,
            )
        logger.info("[DIAGNOSTIC] SUCCESS: memory_consent updated to %s for learner_id=%s", consent, user_id)
        return True
    except Exception as exc:
        logger.error("[DIAGNOSTIC] update_consent SQL error [%s]: %s", type(exc).__name__, exc)
        reset_pool()
        return False


async def save_memory(user_id: str, memory_data: dict, new_consent_choice: Optional[bool] = None) -> bool:
    """Upsert learner memory for user_id, strictly enforcing memory_consent."""
    logger.info(
        "[DIAGNOSTIC] save_memory REACHED for learner_id=%s with data keys=%s | new_consent_choice=%s",
        user_id,
        list(memory_data.keys()),
        new_consent_choice,
    )
    pool = await get_pool()
    if pool is None:
        logger.warning("[DIAGNOSTIC] save_memory: get_pool() returned None — DB unavailable, save aborted.")
        return False

    now = datetime.now(timezone.utc)

    try:
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT * FROM learner_memory WHERE user_id = $1", user_id
            )

            # Determine effective consent
            if new_consent_choice is not None:
                effective_consent = new_consent_choice
            elif existing:
                effective_consent = existing["memory_consent"]
            else:
                effective_consent = None

            # Security gate: backend enforcement
            if effective_consent is not True:
                logger.warning(
                    "[DIAGNOSTIC] save_memory REJECTED for learner_id=%s — effective memory_consent is %s (must be True)",
                    user_id,
                    effective_consent,
                )
                return False

            def _pick(key: str, new_val: Any, default: Any = None) -> Any:
                """Return new_val if non-empty, else preserve existing value."""
                if new_val not in (None, "", [], {}):
                    return new_val
                if existing:
                    return existing[key]
                return default

            name = _pick("name", memory_data.get("name"), "")
            language_preference = _pick(
                "language_preference", memory_data.get("language_preference"), ""
            )
            german_level = _pick("german_level", memory_data.get("german_level"), "")
            learning_goal = _pick(
                "learning_goal", memory_data.get("learning_goal"), ""
            )
            topics_covered = _pick(
                "topics_covered", memory_data.get("topics_covered"), []
            )
            common_mistakes = _pick(
                "common_mistakes", memory_data.get("common_mistakes"), []
            )

            if existing is None:
                logger.info("[DIAGNOSTIC] Executing INSERT INTO learner_memory for learner_id=%s", user_id)
                await conn.execute(
                    """
                    INSERT INTO learner_memory (
                        user_id, name, language_preference, german_level,
                        learning_goal, topics_covered, common_mistakes,
                        memory_consent, last_interaction, created_at, updated_at
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                    """,
                    user_id,
                    name,
                    language_preference,
                    german_level,
                    learning_goal,
                    topics_covered,
                    common_mistakes,
                    True,
                    now,
                    now,
                    now,
                )
                logger.info("[DIAGNOSTIC] SUCCESS: INSERT completed for learner_id=%s", user_id)
            else:
                logger.info("[DIAGNOSTIC] Executing UPDATE learner_memory for learner_id=%s", user_id)
                merged_topics = list(
                    set((existing["topics_covered"] or []) + (topics_covered or []))
                )
                merged_mistakes = list(
                    set(
                        (existing["common_mistakes"] or []) + (common_mistakes or [])
                    )
                )

                await conn.execute(
                    """
                    UPDATE learner_memory SET
                        name               = $2,
                        language_preference = $3,
                        german_level       = $4,
                        learning_goal      = $5,
                        topics_covered     = $6,
                        common_mistakes    = $7,
                        memory_consent     = TRUE,
                        last_interaction   = $8,
                        updated_at         = $9
                    WHERE user_id = $1
                    """,
                    user_id,
                    name,
                    language_preference,
                    german_level,
                    learning_goal,
                    merged_topics,
                    merged_mistakes,
                    now,
                    now,
                )
                logger.info("[DIAGNOSTIC] SUCCESS: UPDATE completed for learner_id=%s", user_id)

        return True

    except Exception as exc:
        logger.error("[DIAGNOSTIC] save_memory SQL EXCEPTION [%s]: %s", type(exc).__name__, exc)
        reset_pool()
        return False

