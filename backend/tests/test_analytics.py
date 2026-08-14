"""
test_analytics.py — Unit tests for Day 8 call analytics writer.
"""

import pytest
import uuid
import os
from analytics import record_call
from db import get_pool


@pytest.mark.asyncio
async def test_record_call_executes_safely() -> None:
    """Verify record_call runs without raising exceptions and inserts row if DB available."""
    test_session_id = f"test-session-{uuid.uuid4().hex[:8]}"
    test_learner_id = f"test-learner-{uuid.uuid4().hex[:8]}"

    # Invoke record_call
    await record_call(
        session_id=test_session_id,
        learner_id=test_learner_id,
        channel="browser",
        outcome="success",
    )

    pool = await get_pool()
    if pool is not None:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT session_id, learner_id, channel, outcome FROM call_analytics WHERE session_id = $1",
                test_session_id,
            )
            assert row is not None
            assert row["session_id"] == test_session_id
            assert row["learner_id"] == test_learner_id
            assert row["channel"] == "browser"
            assert row["outcome"] == "success"
            
            # Clean up test row
            await conn.execute("DELETE FROM call_analytics WHERE session_id = $1", test_session_id)
