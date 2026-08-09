"""
migrate.py — One-time database migration for DeutschMate learner memory.

Run once to create the learner_memory table:

    cd backend
    python src/migrate.py

Reads DATABASE_URL from .env.local (same as the agent).
"""

import asyncio
import logging
import os
import sys

import asyncpg
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate")

DDL = """
CREATE TABLE IF NOT EXISTS learner_memory (
    user_id             TEXT PRIMARY KEY,
    name                TEXT        NOT NULL DEFAULT '',
    language_preference TEXT        NOT NULL DEFAULT '',
    german_level        TEXT        NOT NULL DEFAULT '',
    learning_goal       TEXT        NOT NULL DEFAULT '',
    topics_covered      TEXT[]      NOT NULL DEFAULT '{}',
    common_mistakes     TEXT[]      NOT NULL DEFAULT '{}',
    memory_consent      BOOLEAN     DEFAULT NULL,
    last_interaction    TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Safely add memory_consent column to existing installations if missing
ALTER TABLE learner_memory ADD COLUMN IF NOT EXISTS memory_consent BOOLEAN DEFAULT NULL;

-- Index for fast lookup by user_id (already covered by PK, but explicit)
CREATE INDEX IF NOT EXISTS idx_learner_memory_user_id
    ON learner_memory (user_id);

-- Index for querying recently active learners
CREATE INDEX IF NOT EXISTS idx_learner_memory_last_interaction
    ON learner_memory (last_interaction DESC NULLS LAST);
"""


async def run_migration() -> None:
    load_dotenv(".env.local")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error(
            "DATABASE_URL is not set. "
            "Add it to backend/.env.local and re-run this script."
        )
        sys.exit(1)

    logger.info("Connecting to PostgreSQL …")
    try:
        conn = await asyncpg.connect(dsn=database_url)
    except Exception as exc:
        logger.error("Connection failed: %s", exc)
        sys.exit(1)

    try:
        logger.info("Running DDL …")
        await conn.execute(DDL)
        logger.info("✓ learner_memory table is ready.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migration())
