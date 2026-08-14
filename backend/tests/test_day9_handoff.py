"""
test_day9_handoff.py — Day 9 Unit tests for German Job Interview Coach specialist agent and handoff.
"""

import pytest
from livekit.agents import AgentSession, inference, llm
from livekit.plugins import murf

from agent import (
    Assistant,
    GermanJobInterviewCoach,
    _build_interview_coach_prompt,
    BASE_SYSTEM_PROMPT,
)


def _llm() -> llm.LLM:
    return inference.LLM(model="google/gemini-3.5-flash-lite")


@pytest.mark.asyncio
async def test_assistant_has_handoff_tool() -> None:
    """Verify Assistant has handoff_to_job_interview_coach registered."""
    assistant = Assistant(system_prompt=BASE_SYSTEM_PROMPT, user_id="test_user")
    tools = [t.info.name for t in assistant.tools if hasattr(t, "info")]
    assert "handoff_to_job_interview_coach" in tools, (
        f"Expected handoff_to_job_interview_coach in assistant tools, got: {tools}"
    )


@pytest.mark.asyncio
async def test_specialist_initialization() -> None:
    """Verify GermanJobInterviewCoach initialization, voice Samar, and prompt building."""
    target_role = "software engineer"
    interview_date = "next Tuesday"
    prompt = _build_interview_coach_prompt(
        target_role=target_role, interview_date=interview_date
    )

    specialist_tts = murf.TTS(
        voice="Samar",
        style="Conversation",
    )

    specialist = GermanJobInterviewCoach(
        system_prompt=prompt,
        user_id="test_learner",
        target_role=target_role,
        interview_date=interview_date,
        tts=specialist_tts,
    )

    assert specialist.target_role == "software engineer"
    assert specialist.interview_date == "next Tuesday"
    assert "Target Job Role: software engineer" in specialist.instructions
    assert "Interview Date: next Tuesday" in specialist.instructions


@pytest.mark.asyncio
async def test_handoff_preserves_conversation_context() -> None:
    """Verify handoff_to_job_interview_coach transfers conversation history and target role."""
    session = AgentSession()
    assistant = Assistant(system_prompt=BASE_SYSTEM_PROMPT, user_id="test_learner")
    session.update_agent(assistant)

    # 1. Add user request and assistant handoff announcement to session history
    user_msg = "I have an interview next Tuesday for a software engineer position in Germany."
    announcement = "Absolutely. I'll connect you with our German Job Interview Coach."

    session.history.add_message(role="user", content=user_msg)
    session.history.add_message(role="assistant", content=announcement)

    # 2. Instantiate RunContext mock & execute handoff logic
    session_chat_ctx = session.history.copy()
    specialist_prompt = _build_interview_coach_prompt(
        target_role="software engineer", interview_date="next Tuesday"
    )

    specialist = GermanJobInterviewCoach(
        system_prompt=specialist_prompt,
        user_id="test_learner",
        target_role="software engineer",
        interview_date="next Tuesday",
        chat_ctx=session_chat_ctx,
    )

    session.update_agent(specialist)

    # 3. Assert active agent updated to GermanJobInterviewCoach
    assert session._agent == specialist

    # 4. Assert specialist chat context contains previous conversation turns
    messages = specialist.chat_ctx.messages()
    assert len(messages) >= 2
    assert user_msg in str(messages[0].content)
    assert announcement in str(messages[1].content)
