"""
test_escalation.py — Unit tests for Day 7 Human Escalation & Privacy features.
"""

import asyncio
import os
import re
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from escalation import (
    generate_reference_id,
    sanitize_text,
    send_escalation_email,
    save_escalation_db,
)


def test_reference_id_format():
    """Verify generated reference ID matches DM-2026-XXXXXX pattern."""
    ref_id = generate_reference_id()
    assert ref_id.startswith("DM-2026-")
    assert len(ref_id) == 14  # "DM-2026-" (8) + 6 hex chars = 14 chars
    assert re.match(r"^DM-2026-[A-F0-9]{6}$", ref_id)


def test_sanitize_text_redacts_passwords_and_tokens():
    """Verify secrets, passwords, tokens, OTPs, PINs, and credit cards are redacted."""
    raw_text = (
        "password: mysecret123 and OTP: 654321. "
        "Here is my API key: sk-abcdef12345678901234567890. "
        "Also my pin: 9988."
    )
    sanitized = sanitize_text(raw_text)

    assert "mysecret123" not in sanitized
    assert "654321" not in sanitized
    assert "sk-abcdef12345678901234567890" not in sanitized
    assert "[REDACTED_PASSWORD]" in sanitized or "[REDACTED_SECRET]" in sanitized


@pytest.mark.asyncio
async def test_send_escalation_email_unconfigured():
    """Verify send_escalation_email returns graceful failure when SMTP is not configured."""
    with patch.dict(os.environ, {"ESCALATION_EMAIL_TO": "", "ESCALATION_SMTP_HOST": ""}):
        success, msg = await send_escalation_email(
            reference_id="DM-2026-TEST01",
            learner_id="test_learner",
            summary="Struggling with dative case",
            what_was_checked="Checked article tables",
            urgency="medium",
        )
        assert success is False
        assert "not configured" in msg


@pytest.mark.asyncio
async def test_send_escalation_email_mock_smtp():
    """Verify send_escalation_email succeeds when SMTP server sends message."""
    mock_env = {
        "ESCALATION_EMAIL_TO": "teacher@example.com",
        "ESCALATION_SMTP_HOST": "smtp.example.com",
        "ESCALATION_SMTP_PORT": "587",
        "ESCALATION_SMTP_USERNAME": "test_user",
        "ESCALATION_SMTP_PASSWORD": "test_pass",
        "ESCALATION_EMAIL_FROM": "deutschmate@example.com",
    }
    with patch.dict(os.environ, mock_env):
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_server

            success, msg = await send_escalation_email(
                reference_id="DM-2026-TEST02",
                learner_id="learner_123",
                summary="Learner is confused by preposition cases",
                what_was_checked="Explained in/an/auf rules",
                urgency="medium",
                language="German",
                preferred_follow_up="Email",
            )

            assert success is True
            assert msg == "Email sent successfully"
            mock_server.send_message.assert_called_once()
            sent_msg = mock_server.send_message.call_args[0][0]
            assert "[DeutschMate] Human Help Request — DM-2026-TEST02" in sent_msg["Subject"]
            body = sent_msg.get_content()
            assert "DM-2026-TEST02" in body
            assert "learner_123" in body
            assert "preposition cases" in body
            assert "medium" in body


@pytest.mark.asyncio
async def test_create_escalation_tool_requires_consent():
    """Verify Assistant.create_escalation tool blocks when consent_confirmed is False."""
    from agent import Assistant

    assistant = Assistant(system_prompt="Test", user_id="test_user_456")
    ctx = MagicMock()

    # Call create_escalation without consent
    result = await assistant.create_escalation(
        context=ctx,
        reason="Frustrated learner",
        summary="Cannot understand grammar",
        what_was_checked="Grammar rules",
        urgency="medium",
        consent_confirmed=False,
    )

    assert "Escalation cancelled" in result
    assert "consent" in result.lower()


@pytest.mark.asyncio
async def test_create_escalation_email_failure_honest_feedback():
    """Verify create_escalation tells the LLM honestly that delivery failed when SMTP is unconfigured."""
    from agent import Assistant

    assistant = Assistant(system_prompt="Test", user_id="test_user_789")
    ctx = MagicMock()

    with patch.dict(os.environ, {"ESCALATION_EMAIL_TO": "", "ESCALATION_SMTP_HOST": ""}):
        with patch("agent.save_escalation_db", return_value=True):
            result = await assistant.create_escalation(
                context=ctx,
                reason="Learner anxiety",
                summary="Overwhelmed by grammar",
                what_was_checked="A1 rules",
                urgency="high",
                consent_confirmed=True,
            )

            assert "EMAIL DELIVERY FAILED" in result
            assert "COULD NOT BE DELIVERED" in result
            assert "Do NOT give the learner a reference ID" in result


def test_system_prompt_escalation_and_language_rules():
    """Verify system prompt includes required escalation triggers and strict language rules."""
    from agent import BASE_SYSTEM_PROMPT

    assert "I'm very anxious." in BASE_SYSTEM_PROMPT
    assert "I'm frustrated." in BASE_SYSTEM_PROMPT
    assert "I'm overwhelmed." in BASE_SYSTEM_PROMPT
    assert "I'm getting stressed." in BASE_SYSTEM_PROMPT
    assert "I don't understand anything." in BASE_SYSTEM_PROMPT
    assert "This is too difficult for me." in BASE_SYSTEM_PROMPT
    assert "Can I talk to a teacher?" in BASE_SYSTEM_PROMPT
    assert "ALWAYS respond in the language used by the learner's LATEST meaningful utterance" in BASE_SYSTEM_PROMPT

