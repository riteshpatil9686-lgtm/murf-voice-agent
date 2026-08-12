"""
escalation.py — Human escalation & email dispatcher for DeutschMate (Day 7).

Provides:
  - generate_reference_id() -> str (Format: DM-2026-XXXXXX)
  - sanitize_text(text: str) -> str (Masks/redacts passwords, OTPs, PINs, keys, tokens)
  - send_escalation_email(...) -> tuple[bool, str] (Sends email via SMTP using asyncio.to_thread)
  - save_escalation_db(...) -> bool (Saves escalation request to PostgreSQL)
"""

import asyncio
import logging
import os
import re
import smtplib
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Optional

from db import get_pool, reset_pool

logger = logging.getLogger("agent.escalation")

# Regex patterns for secret/sensitive data redaction
SECRET_PATTERNS = [
    # Passwords / Tokens / Keys labeled in text
    (re.compile(r"(?i)\b(password|passwd|passcode|token|api[_-]?key|secret|otp|pin)\s*[:=]\s*\S+"), r"\1: [REDACTED_SECRET]"),
    # Bearer tokens / JWTs / Private keys / API keys (e.g. sk_..., ghp_..., eyJ...)
    (re.compile(r"\b(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,}|bearer\s+[a-zA-Z0-9._\-]+|eyJ[a-zA-Z0-9._\-]+)\b", re.IGNORECASE), "[REDACTED_TOKEN]"),
    # Credit Card numbers (13-16 digits)
    (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "[REDACTED_CARD]"),
    # Standard 4-8 digit standalone OTPs/PINs explicitly labeled
    (re.compile(r"(?i)\b(otp|pin|verification code|one time password)\s*[:=]?\s*\d{4,8}\b"), r"\1: [REDACTED_PIN]"),
]


def generate_reference_id() -> str:
    """Generate a unique human-readable reference ID matching format DM-2026-XXXXXX."""
    random_code = uuid.uuid4().hex[:6].upper()
    return f"DM-2026-{random_code}"


def sanitize_text(text: str) -> str:
    """Sanitize input text to remove sensitive credentials (passwords, OTPs, PINs, API keys, tokens)."""
    if not text:
        return ""
    sanitized = text
    for pattern, replacement in SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


async def save_escalation_db(
    reference_id: str,
    learner_id: str,
    reason: str,
    summary: str,
    what_was_checked: str,
    urgency: str,
    language: str,
    preferred_follow_up: str,
    status: str = "open",
) -> bool:
    """Save the escalation request to the PostgreSQL database if available."""
    pool = await get_pool()
    if pool is None:
        logger.warning("[ESCALATION] save_escalation_db: DB unavailable — skipping database persistence.")
        return False

    now = datetime.now(timezone.utc)
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO escalation_requests (
                    reference_id, learner_id, reason, summary, what_was_checked,
                    urgency, language, preferred_follow_up, status, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (reference_id) DO NOTHING
                """,
                reference_id,
                learner_id,
                reason,
                summary,
                what_was_checked,
                urgency.lower(),
                language,
                preferred_follow_up,
                status,
                now,
            )
        logger.info("[ESCALATION] Saved escalation request %s to database.", reference_id)
        return True
    except Exception as exc:
        logger.error("[ESCALATION] save_escalation_db SQL error [%s]: %s", type(exc).__name__, exc)
        reset_pool()
        return False


def _send_smtp_email_sync(
    reference_id: str,
    learner_id: str,
    summary: str,
    what_was_checked: str,
    urgency: str,
    language: str,
    preferred_follow_up: str,
) -> tuple[bool, str]:
    """Synchronous SMTP email dispatcher."""
    email_to = os.getenv("ESCALATION_EMAIL_TO", "").strip()
    smtp_host = os.getenv("ESCALATION_SMTP_HOST", "").strip()
    smtp_port_str = os.getenv("ESCALATION_SMTP_PORT", "587").strip()
    smtp_user = os.getenv("ESCALATION_SMTP_USERNAME", "").strip()
    smtp_pass = os.getenv("ESCALATION_SMTP_PASSWORD", "").strip()
    email_from = os.getenv("ESCALATION_EMAIL_FROM", "").strip() or smtp_user or "deutschmate-noreply@example.com"

    if not email_to or not smtp_host:
        msg = "ESCALATION_EMAIL_TO or ESCALATION_SMTP_HOST is not configured in environment."
        logger.error("[ESCALATION] %s", msg)
        return False, msg

    try:
        smtp_port = int(smtp_port_str)
    except ValueError:
        smtp_port = 587

    # Construct concise Email message
    msg = EmailMessage()
    msg["Subject"] = f"[DeutschMate] Human Help Request — {reference_id}"
    msg["From"] = email_from
    msg["To"] = email_to

    safe_learner = sanitize_text(learner_id or "Anonymous Learner")
    safe_summary = sanitize_text(summary)
    safe_checked = sanitize_text(what_was_checked)
    safe_urgency = urgency.lower() if urgency.lower() in ("low", "medium", "high") else "medium"
    safe_lang = sanitize_text(language or "English")
    safe_followup = sanitize_text(preferred_follow_up or "Email")

    body_text = f"""Reference ID:
{reference_id}

Learner:
{safe_learner}

What happened:
{safe_summary}

What DeutschMate already checked:
{safe_checked}

Urgency:
{safe_urgency}

Language:
{safe_lang}

Preferred follow-up method:
{safe_followup}
"""
    msg.set_content(body_text)

    try:
        logger.info("[ESCALATION] Connecting to SMTP server %s:%d ...", smtp_host, smtp_port)
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as server:
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.ehlo()
                try:
                    server.starttls()
                    server.ehlo()
                except smtplib.SMTPNotSupportedError:
                    pass
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.send_message(msg)

        logger.info("[ESCALATION] Email sent successfully for request %s to %s", reference_id, email_to)
        return True, "Email sent successfully"

    except Exception as exc:
        # Log technical error without exposing credentials or passwords
        logger.error(
            "[ESCALATION] Failed to send email for request %s via %s:%d [%s]: %s",
            reference_id,
            smtp_host,
            smtp_port,
            type(exc).__name__,
            exc,
        )
        return False, f"SMTP delivery error: {type(exc).__name__}"


async def send_escalation_email(
    reference_id: str,
    learner_id: str,
    summary: str,
    what_was_checked: str,
    urgency: str,
    language: str = "English",
    preferred_follow_up: str = "Email",
) -> tuple[bool, str]:
    """Asynchronous non-blocking wrapper to send escalation email via SMTP thread pool."""
    return await asyncio.to_thread(
        _send_smtp_email_sync,
        reference_id,
        learner_id,
        summary,
        what_was_checked,
        urgency,
        language,
        preferred_follow_up,
    )
