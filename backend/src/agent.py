"""
agent.py — DeutschMate voice agent with persistent learner memory and German practice tool.

Memory (Day 4):
  - Generates / persists an anonymous learner_id stored in the LiveKit
    room metadata (or falls back to ctx.room.name as a stable session key).
  - On session start: calls lookup_user() to greet returning learners.
  - During conversation: tracks name, level, goal, topics, mistakes in state.
  - After gathering information: asks consent before calling save_memory().
  - If DB is unavailable: continues normally; never fabricates memory.

Practice Tool (Day 5):
  - get_german_practice() tool retrieves REAL German practice exercises.
  - Primary source: German Language Learning API (https://german-language.onrender.com).
  - Local fallback dataset: backend/data/german_exercises.json when external API
    is rate limited (429), times out, or unavailable.

Outbound Calling (Day 6):
  - outbound_practice_session() entrypoint handles dispatched "Daily German
    Practice Call" jobs.
  - Uses ctx.api.sip.create_sip_participant() with a pre-configured LiveKit
    SIP Outbound Trunk to dial the learner's Linphone SIP address.
  - Learner identity (Google sub) is passed via job metadata so Day 4 memory
    is loaded identically to an inbound web session.
  - Agent speaks first upon answer with a transparent introduction.
  - Gracefully handles: no-answer, rejection, voicemail, and SIP errors.
"""

import asyncio
import json
import logging
import os
import random
import urllib.error
import urllib.parse
import urllib.request
import uuid

from dotenv import load_dotenv
from livekit import rtc, api
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    cli,
    function_tool,
    get_job_context,
    inference,
    tokenize,
    room_io,
    RunContext,
    UserInputTranscribedEvent,
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

# Memory layer — safe to import even if asyncpg is not yet installed
try:
    from memory import lookup_user, save_memory, update_consent
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False

# Escalation layer — safe to import even if escalation.py fails
try:
    from escalation import (
        generate_reference_id,
        sanitize_text,
        send_escalation_email,
        save_escalation_db,
    )
    ESCALATION_AVAILABLE = True
except ImportError:
    ESCALATION_AVAILABLE = False

logger = logging.getLogger("agent")

load_dotenv(".env.local")
load_dotenv(".env")
load_dotenv()

# ---------------------------------------------------------------------------
# Day 6 — Outbound SIP trunk (read once at startup; None if not configured)
# ---------------------------------------------------------------------------
SIP_OUTBOUND_TRUNK_ID: str | None = os.getenv("SIP_OUTBOUND_TRUNK_ID", "").strip() or None

FALLBACK_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "german_exercises.json",
)

# ---------------------------------------------------------------------------
# Helper functions for Day 5 German Learning Practice API & Fallback
# ---------------------------------------------------------------------------

def _normalize_cefr(level_str: str) -> str:
    """Normalize user or memory level strings to standard CEFR levels."""
    lvl = (level_str or "").strip().lower()
    if lvl in ("a1", "beginner", "elementar"):
        return "A1"
    elif lvl in ("a2", "grundlegend"):
        return "A2"
    elif lvl in ("b1", "intermediate", "mittelstufe"):
        return "B1"
    elif lvl in ("b2", "fortgeschritten", "advanced"):
        return "B2"
    elif lvl in ("c1", "c2", "expert"):
        return "C1"
    return "A1"


def _load_local_fallback_exercise(level: str = "", topic: str = "", practice_type: str = "") -> dict | None:
    """Load a practice exercise from local JSON dataset when external API is unreachable."""
    if not os.path.exists(FALLBACK_DATA_PATH):
        logger.error("[DIAGNOSTIC] Fallback data file missing at %s", FALLBACK_DATA_PATH)
        return None

    try:
        with open(FALLBACK_DATA_PATH, "r", encoding="utf-8") as f:
            exercises = json.load(f)

        if not exercises or not isinstance(exercises, list):
            return None

        norm_level = _normalize_cefr(level).lower()
        level_map = {
            "a1": ["beginner", "a1"],
            "a2": ["intermediate", "a2"],
            "b1": ["intermediate", "b1"],
            "b2": ["advanced", "b2"],
            "c1": ["advanced", "c1"],
        }
        valid_level_tags = level_map.get(norm_level, ["beginner", "a1"])

        pool = [
            e for e in exercises
            if e.get("level", "").lower() in valid_level_tags
        ]
        if not pool:
            pool = exercises

        if topic:
            t_lower = topic.strip().lower()
            topic_filtered = [e for e in pool if t_lower in e.get("topic", "").lower()]
            if topic_filtered:
                pool = topic_filtered

        if practice_type:
            pt_lower = practice_type.strip().lower()
            pt_filtered = [e for e in pool if pt_lower in e.get("type", "").lower()]
            if pt_filtered:
                pool = pt_filtered

        chosen = random.choice(pool)
        return {
            "status": "success",
            "source": "local_fallback",
            "note": "The online learning library isn't available right now, so I'll use an offline exercise instead.",
            "level": chosen.get("level", level or "beginner"),
            "topic": chosen.get("topic", topic or "general"),
            "practice_type": chosen.get("type", practice_type or "general"),
            "question": chosen.get("question", ""),
            "answer": chosen.get("answer", ""),
        }
    except Exception as exc:
        logger.error("[DIAGNOSTIC] Error reading local fallback exercises: %s", exc)
        return None


def _fetch_external_german_practice_sync(level: str = "", topic: str = "", practice_type: str = "") -> dict | None:
    """Synchronous fetch from the German Language Learning API (https://german-language.onrender.com)."""
    api_key = os.getenv("GERMAN_API_KEY", "demo-key-12345")
    base_url = "https://german-language.onrender.com"
    headers = {
        "X-API-Key": api_key,
        "User-Agent": "DeutschMate/1.0",
    }
    cefr = _normalize_cefr(level)
    pt = (practice_type or "").strip().lower()
    top = (topic or "").strip().lower()

    logger.info("Fetching German practice from external API (level=%s, topic=%s, type=%s)", cefr, top, pt)

    try:
        if pt == "grammar" or top == "grammar":
            url = f"{base_url}/grammar?limit=10"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            if not items:
                return None
            item = random.choice(items)
            title = item.get("title") or item.get("category") or "German Grammar Rule"
            rule = item.get("rule") or item.get("description") or item.get("explanation") or ""
            examples = item.get("examples") or []
            ex_str = f" Example: '{examples[0]}'" if examples else ""
            return {
                "status": "success",
                "source": "external_api",
                "level": cefr,
                "topic": item.get("category", "grammar"),
                "practice_type": "grammar",
                "question": f"Grammar Topic: {title}. Rule: {rule}. Can you create a German sentence using this rule?",
                "answer": f"Rule: {rule}.{ex_str}",
            }

        elif pt == "vocabulary" or top == "vocabulary":
            if top and top != "vocabulary":
                url = f"{base_url}/vocab/search?q={urllib.parse.quote(top)}&limit=10"
            else:
                url = f"{base_url}/vocab?level={cefr.lower()}&limit=20"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            if not items:
                return None
            item = random.choice(items)
            eng = item.get("english", "")
            ger = item.get("german", "")
            gender = item.get("gender") or ""
            pos = item.get("pos", "word")
            gender_str = f" ({gender})" if gender else ""
            return {
                "status": "success",
                "source": "external_api",
                "level": item.get("level", cefr),
                "topic": "vocabulary",
                "practice_type": "vocabulary",
                "question": f"What is the German word for '{eng}' ({pos})?",
                "answer": f"The German word is '{ger}'{gender_str}.",
            }

        else:
            # Default sentence translation practice
            url = f"{base_url}/sentences/random?level={cefr}&count=5"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            if not items:
                return None
            item = random.choice(items)
            sen_de = item.get("sentence_de", "")
            sen_en = item.get("sentence_en", "")
            return {
                "status": "success",
                "source": "external_api",
                "level": item.get("level", cefr),
                "topic": topic or "general_practice",
                "practice_type": practice_type or "sentence_translation",
                "question": f"Translate to German: '{sen_en}'",
                "answer": f"'{sen_de}'",
            }
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.warning("[DIAGNOSTIC] External learning API unavailable or failed [%s]: %s", type(exc).__name__, exc)
        return None

# ---------------------------------------------------------------------------
# System prompt — memory context & practice rules injected.
# ---------------------------------------------------------------------------
BASE_SYSTEM_PROMPT = """\
You are DeutschMate, a friendly and patient AI German Tutor.

Your goal is to help users learn German through natural voice conversations.

You can:
- Teach German vocabulary and grammar.
- Help users practice pronunciation.
- Explain German words and sentences in English.
- Correct mistakes politely and explain why they are incorrect.
- Conduct beginner to advanced German conversations.
- Give quizzes and speaking exercises using the `get_german_practice` tool.
- Teach common phrases used in travel, work, school, and daily life.
- Encourage users to respond in German whenever possible.

Teaching Style:
- Speak clearly and naturally.
- Keep responses short because this is a voice conversation.
- Start with simple language unless the user asks for advanced topics.
- If the user makes a mistake, first acknowledge their effort, then provide
  the correct German and a brief explanation.
- Ask follow-up questions to keep the conversation going.

Examples:
User: "How do I say 'Good morning'?"
You: "You say 'Guten Morgen.' Can you repeat it?"

User: "Ich bin gut."
You: "Very good! A more natural response when someone asks 'Wie geht's?' is
'Mir geht es gut.' That means 'I am doing well.'"

---
ONE-TIME MEMORY CONSENT & AUTOMATIC SAVING RULES:

1. CONSENT STATES:
   - UNSET (NULL / New Learner):
     Ask ONCE for memory consent during or early in the lesson:
     "I can remember your German level, learning goals, and learning progress so I can continue from where we left off. Would you like me to remember these?"
   - GRANTED (TRUE / Returning Learner):
     Consent is ALREADY GRANTED. Greet the learner by name and mention what they practiced last if applicable.
     Do NOT ask for consent again! Automatically save new learning facts silently as they are mentioned.
   - DENIED (FALSE / Declined):
     User declined memory saving. Do NOT save memory and do NOT ask again.

2. MULTILINGUAL CONSENT INTENT:
   - Any clear affirmative answer (e.g. "Yes", "Sure", "Haan", "Haan, yaad rakhna", "Haan, save kar lo", "Theek hai", "Ja, bitte", or any English/Hindi/Hinglish/German equivalent meaning yes) = CALL `set_memory_consent(consent_granted=True)`.
   - Any refusal (e.g. "No", "Nahi", "Nahi, save mat karna", "Nein, bitte nicht", or any equivalent meaning no) = CALL `set_memory_consent(consent_granted=False)`.
   - If genuinely ambiguous, ask once for clarification.

3. AUTOMATIC MEMORY SAVING:
   - Once memory consent is TRUE, AUTOMATICALLY call `save_learner_memory(...)` whenever the user mentions:
     * Their name
     * Their German level (e.g., beginner, A1, B2)
     * Their learning goals (e.g., German for job, travel)
     * Topics covered in the lesson (e.g., word order, greetings)
     * Recurring mistakes (e.g., verb position errors)
   - Do NOT ask permission again for individual facts.
   - Do NOT store full conversation transcripts.

4. CHANGE OF MIND:
   - If a user who previously declined later says to save their progress (e.g., "You can save my details now"), call `set_memory_consent(consent_granted=True)`.
   - If a user who previously agreed later says to stop saving (e.g., "Stop saving my details"), call `set_memory_consent(consent_granted=False)`.

5. LANGUAGE & SCRIPT — STRICT RULE

STRICT RULE FOR RESPONSE LANGUAGE:
ALWAYS respond in the language used by the learner's LATEST meaningful utterance, unless the learner explicitly requests another language.

1. LATEST UTTERANCE DRIVES LANGUAGE:
   - If the user's latest utterance is in English (e.g. "I'm very anxious, I'm not understanding." or "Can you connect me with a teacher?"), respond strictly in ENGLISH.
   - If the user's latest utterance is in Hindi / Hinglish (e.g. "Mujhe German samajh nahi aa raha." or "Mujhe bahut anxiety ho rahi hai"), respond in HINDI / HINGLISH.
   - If the user's latest utterance is in German (e.g. "Ich verstehe das nicht."), respond in GERMAN.

2. DO NOT INFER OR ASSUME HINGLISH / HINDI:
   - NEVER infer Hinglish or Hindi merely because the learner's profile, name, location, or previous conversation history suggests India or Hinglish.
   - DO NOT switch to Hindi just because the learner has previously spoken Hindi or has a saved language preference. The LATEST user utterance is the absolute primary signal.
   - For mixed-language utterances, use the dominant language of the latest utterance. If genuinely ambiguous, continue in the language most recently used by the learner rather than switching unexpectedly.

3. SCRIPT PRESERVATION:
   - Hindi → Devanagari script (e.g. "बिल्कुल!")
   - German → Latin script with ä, ö, ü, ß
   - English → Latin script

4. ESCALATION TOOL LANGUAGE PARAMETER:
   - The `language` field passed to `create_escalation` MUST reflect the learner's actual conversation language for the current session (e.g. "English", "Hindi", "German", "Hinglish"). If the user spoke English, set language="English", NOT "Hinglish".

5. Always respond in the language of the learner's latest meaningful utterance.

For Hindi:
- Use natural Indian Hindi pronunciation and phrasing.
- Hindi must be written in Devanagari script.
- Do not use Romanized Hindi/Hinglish when the learner is speaking Hindi.
- Do not use an English/Western Hindi accent.
- Prefer natural Indian Hindi vocabulary and sentence structure.

For English:
- Respond in English.

For German:
- Respond in German

 TTS PRONUNCIATION — INDIAN HINDI

When responding in Hindi:
- Use natural Indian Hindi pronunciation.
- Speak Hindi as an Indian Hindi speaker would naturally speak it.
- Do NOT pronounce Hindi using an American, British, European, or other foreign accent.
- Do NOT use an English-accented pronunciation of Hindi words.
- Maintain natural Indian Hindi rhythm, pronunciation, and intonation.
- If the learner speaks Hindi, the spoken response must sound like natural Indian Hindi, not English spoken with Hindi words.
---
6. EXERCISE PRACTICE & ANSWER PROTECTION RULES:
- Call `get_german_practice` when the user asks for a German exercise, quiz, vocabulary practice, grammar exercise, translation challenge, speaking exercise, or asks 'give me something to practice'.
- Do NOT call `get_german_practice` for casual conversation or general questions that do not require retrieving exercise content.
- CRITICAL EXERCISE ANSWER PROTECTION RULE: When presenting an exercise from `get_german_practice`, ask the learner the question FIRST. DO NOT reveal the correct answer until AFTER the learner has made an attempt or explicitly requested the answer.
- If the tool result contains a `note` (e.g. indicating offline fallback), inform the user naturally (e.g., "The online learning library isn't available right now, so I'll use an offline exercise instead.") before asking the question.
---
7. HUMAN TEACHER ESCALATION RULES (DAY 7):

- ESCALATION TRIGGERS (WHEN TO OFFER HUMAN TEACHER ESCALATION):
  You MUST recognize these TWO situations as valid reasons to OFFER escalation to a human teacher:
  1. Significant learner distress, frustration, anxiety, stress, or feeling overwhelmed while struggling to learn.
     Examples that MUST trigger an escalation OFFER:
     * "I'm very anxious."
     * "I'm frustrated."
     * "I'm overwhelmed."
     * "I'm getting stressed."
     * "I don't understand anything."
     * "This is too difficult for me."
     * "Mujhe bahut anxiety ho rahi hai aur mujhe samajh nahi aa raha."
  2. Any explicit request for human teacher help or human intervention.
     Examples that MUST trigger an escalation OFFER:
     * "I need help from a teacher."
     * "Can I talk to a teacher?"
     * "I want to speak to a human."
     * "Can you connect me with my teacher?"
     * Grading official exam essays, official exam evaluations, or account/administrative intervention.

- DO NOT ESCALATE normal German learning questions:
  * Do NOT offer or suggest escalation for normal German practice, vocabulary questions, grammar explanations, pronunciation practice, or standard exercises (e.g., "Can you teach me how to introduce myself in German?", "Wie sagt man 'How are you?' auf Deutsch?"). Answer those yourself naturally!

- MANDATORY PRE-CALL CONSENT FLOW:
  * When an escalation trigger occurs, you MUST NOT automatically call `create_escalation`.
  * First acknowledge their feeling in their spoken language, explain what information will be shared, and ask for explicit permission to contact the teacher:
    Example (English): "I understand. It sounds like you're having a difficult time. I can send a short summary to a human teacher so they can help you. It would include what you're struggling with, what we already tried, the urgency, and your preferred follow-up method. Would you like me to send that?"
    Example (Hindi): "मैं समझ सकता हूँ। ऐसा लग रहा है कि आपको परेशानी हो रही है। मैं एक human teacher को आपका summary भेज सकता हूँ जिसमें आपकी problem और urgency होगी। क्या मैं यह संदेश भेज दूँ?"
  * WAIT for the learner's explicit response.

- IF LEARNER SAYS YES / GRANTS PERMISSION (e.g., "Yes", "Please do", "Haan", "Send it"):
  * Call `create_escalation(consent_confirmed=True, ...)` ONLY AFTER the learner explicitly says YES.
  * Check the tool return result carefully!
  * IF TOOL RETURNS SUCCESS (with Reference ID):
    - Tell the learner their Reference ID clearly (e.g. "DM-2026-XXXXXX").
    - Explain honestly what happens next: "A teacher can review it and follow up through the configured support process."
  * IF TOOL RETURNS DELIVERY FAILURE (email failed or unconfigured):
    - DO NOT give a fake reference ID.
    - DO NOT claim the email was sent successfully.
    - Tell the learner honestly that the request could not be delivered right now due to a technical issue, and offer a fallback (e.g. offer to continue helping them directly).

- IF LEARNER SAYS NO / DECLINES PERMISSION (e.g., "No", "No, don't contact my teacher", "Nahi", "Don't send it"):
  * DO NOT call `create_escalation`.
  * DO NOT send an email.
  * Say: "No problem. I won't send anything."
  * Continue the conversation normally in their language.

- PRIVACY & MINIMUM INFORMATION RULE:
  * Include ONLY the minimum useful summary, what was checked, urgency, language.
  * NEVER include passwords, OTPs, PINs, auth tokens, API keys, or private credentials.
  * Do NOT include full conversation transcripts.

- URGENCY & HONESTY:
  * Choose 'low', 'medium', or 'high' urgency based on the situation.
  * Never promise an immediate response unless guaranteed.
"""


def _build_system_prompt(memory: dict | None) -> str:
    """Append returning-learner context to the system prompt when available."""
    if not memory:
        return BASE_SYSTEM_PROMPT + "\n---\nCURRENT CONSENT STATUS: UNSET (NULL - New Learner). Ask for consent once.\n"

    consent_status = memory.get("memory_consent")

    parts = []
    if memory.get("name"):
        parts.append(f"Learner name: {memory['name']}")
    if memory.get("german_level"):
        parts.append(f"German level: {memory['german_level']}")
    if memory.get("learning_goal"):
        parts.append(f"Learning goal: {memory['learning_goal']}")
    if memory.get("language_preference"):
        parts.append(f"Language preference: {memory['language_preference']} (Historical preference only — ALWAYS prioritize the learner's LATEST spoken utterance!)")
    if memory.get("topics_covered"):
        topics = ", ".join(memory["topics_covered"])
        parts.append(f"Topics already covered: {topics}")
    if memory.get("common_mistakes"):
        mistakes = ", ".join(memory["common_mistakes"])
        parts.append(f"Recurring mistakes to watch: {mistakes}")

    memory_block = "\n".join(parts) if parts else "No previous facts recorded yet."

    if consent_status is True:
        consent_header = "CURRENT CONSENT STATUS: GRANTED (TRUE). Do NOT ask for permission again. Automatically call save_learner_memory whenever new facts, level, topics, or mistakes are revealed."
    elif consent_status is False:
        consent_header = "CURRENT CONSENT STATUS: DENIED (FALSE). Do NOT save memory and do NOT ask for consent again."
    else:
        consent_header = "CURRENT CONSENT STATUS: UNSET (NULL - New Learner). Ask for consent once."

    return (
        BASE_SYSTEM_PROMPT
        + f"\n---\n{consent_header}\n"
        + "RETURNING LEARNER CONTEXT (loaded from database — do not read aloud):\n"
        + memory_block
        + "\n"
    )


# ---------------------------------------------------------------------------
# Agent class with memory and practice tools
# ---------------------------------------------------------------------------

class Assistant(Agent):
    """DeutschMate agent. Holds per-session memory state and practice tools."""

    def __init__(self, system_prompt: str, user_id: str) -> None:
        super().__init__(instructions=system_prompt)
        self._user_id = user_id

    @function_tool(
        description="Record the user's ONE-TIME choice regarding memory consent (True to allow remembering, False to decline)."
    )
    async def set_memory_consent(
        self,
        context: RunContext,
        consent_granted: bool,
    ) -> str:
        """Set or update the user's memory consent in PostgreSQL."""
        logger.info(
            "[DIAGNOSTIC] set_memory_consent TOOL CALLED | learner_id=%s | consent_granted=%s",
            self._user_id,
            consent_granted,
        )

        if not MEMORY_AVAILABLE:
            return "Memory system is not available."

        success = await update_consent(self._user_id, consent_granted)
        if success:
            if consent_granted:
                return "Memory consent recorded as GRANTED (TRUE). Automatic memory saving is now active."
            else:
                return "Memory consent recorded as DENIED (FALSE). No learner memory will be saved."
        else:
            return "Failed to update memory consent in database."

    @function_tool(
        description="Automatically save learner's progress, name, German level, topics, and mistakes to the database. Only succeeds if memory consent is TRUE in database."
    )
    async def save_learner_memory(
        self,
        context: RunContext,
        name: str = "",
        language_preference: str = "",
        german_level: str = "",
        learning_goal: str = "",
        topics_covered: list[str] | None = None,
        common_mistakes: list[str] | None = None,
    ) -> str:
        """Save this learner's progress to the database."""
        logger.info(
            "[DIAGNOSTIC] save_learner_memory TOOL CALLED by LLM | authenticated learner_id=%s | name='%s' | level='%s' | topics=%s",
            self._user_id,
            name,
            german_level,
            topics_covered,
        )

        if not MEMORY_AVAILABLE:
            logger.error("[DIAGNOSTIC] save_learner_memory ABORTED — MEMORY_AVAILABLE is False")
            return "Memory system is not available (asyncpg not installed)."

        memory_data = {
            "name": name,
            "language_preference": language_preference,
            "german_level": german_level,
            "learning_goal": learning_goal,
            "topics_covered": topics_covered or [],
            "common_mistakes": common_mistakes or [],
        }

        logger.info("[DIAGNOSTIC] Calling save_memory(user_id=%s, memory_data=%s)", self._user_id, memory_data)
        success = await save_memory(self._user_id, memory_data)
        if success:
            logger.info("[DIAGNOSTIC] SUCCESS: Memory saved to PostgreSQL for authenticated learner_id=%s", self._user_id)
            return "Learner memory updated automatically."
        else:
            logger.warning("[DIAGNOSTIC] SAVE BLOCKED or FAILED: save_memory returned False for authenticated learner_id=%s", self._user_id)
            return "Memory save blocked or database unavailable (Consent must be TRUE in database)."

    @function_tool(
        description=(
            "End the current phone call cleanly. "
            "Call this tool when the learner says they want to hang up, stop, or end the session. "
            "Always let any current spoken response finish before ending."
        )
    )
    async def end_call(self, context: RunContext) -> str:
        """Hang up the outbound call by deleting the LiveKit room."""
        logger.info("[DIAGNOSTIC] end_call TOOL CALLED by LLM for learner_id=%s", self._user_id)
        try:
            job_ctx = get_job_context()
            # Let any current TTS finish before tearing down
            current_speech = context.session.current_speech
            if current_speech:
                await current_speech.wait_for_playout()
            await job_ctx.api.room.delete_room(
                api.DeleteRoomRequest(room=job_ctx.room.name)
            )
            logger.info("[DIAGNOSTIC] Room deleted — call ended cleanly.")
        except Exception as exc:
            logger.warning("[DIAGNOSTIC] end_call: room deletion failed [%s]: %s", type(exc).__name__, exc)
        return "Call ended."

    @function_tool(
        description="Retrieve the current learner's previously saved progress from the database. Does NOT require any user_id parameter."
    )
    async def lookup_learner_memory(
        self,
        context: RunContext,
    ) -> str:
        """Retrieve this learner's previously saved information from the database."""
        logger.info("[DIAGNOSTIC] lookup_learner_memory TOOL CALLED for authenticated learner_id=%s", self._user_id)
        if not MEMORY_AVAILABLE:
            return "Memory system is not available."

        record = await lookup_user(self._user_id)
        if record is None:
            return "No previous record found for this learner."

        summary = {
            "name": record.get("name") or "",
            "german_level": record.get("german_level") or "",
            "learning_goal": record.get("learning_goal") or "",
            "language_preference": record.get("language_preference") or "",
            "topics_covered": record.get("topics_covered") or [],
            "common_mistakes": record.get("common_mistakes") or [],
        }
        return (
            "Returning learner found:\n"
            + "\n".join(f"  {k}: {v}" for k, v in summary.items() if v)
        )

    @function_tool(
        description=(
            "Retrieve a German practice exercise, quiz, vocabulary word, grammar rule, or sentence translation challenge "
            "from the German Learning API (or local exercise library). "
            "Use this tool ONLY when the learner asks for a German exercise, quiz, vocabulary practice, grammar task, "
            "translation challenge, speaking exercise, or asks 'give me something to practice'. "
            "Do NOT call this tool for general conversation, explanations, or simple translation questions."
        )
    )
    async def get_german_practice(
        self,
        context: RunContext,
        level: str = "",
        topic: str = "",
        practice_type: str = "",
    ) -> str:
        """Fetch a German exercise from external API or local fallback dataset.

        Args:
            level: Target German level (e.g., "beginner", "A1", "A2", "B1", "B2", "intermediate").
            topic: Practice topic (e.g., "travel", "introductions", "vocabulary", "grammar", "daily life").
            practice_type: Type of exercise (e.g., "vocabulary", "grammar", "sentence", "translation", "speaking").
        """
        resolved_level = level.strip()
        resolved_topic = topic.strip()
        resolved_type = practice_type.strip()

        logger.info(
            "[DIAGNOSTIC] get_german_practice TOOL CALLED | learner_id=%s | level='%s' | topic='%s' | type='%s'",
            self._user_id,
            resolved_level,
            resolved_topic,
            resolved_type,
        )

        # Day 4 Memory Integration: Fill missing level/topic from learner memory if not explicitly provided
        if (not resolved_level or not resolved_topic) and MEMORY_AVAILABLE:
            try:
                mem = await lookup_user(self._user_id)
                if mem:
                    if not resolved_level and mem.get("german_level"):
                        resolved_level = mem.get("german_level")
                        logger.info("[DIAGNOSTIC] Practice tool auto-resolved level from memory: %s", resolved_level)
                    if not resolved_topic:
                        if mem.get("common_mistakes"):
                            resolved_topic = mem["common_mistakes"][0]
                            logger.info("[DIAGNOSTIC] Practice tool auto-resolved topic from memory common_mistakes: %s", resolved_topic)
                        elif mem.get("topics_covered"):
                            resolved_topic = mem["topics_covered"][-1]
                            logger.info("[DIAGNOSTIC] Practice tool auto-resolved topic from memory topics_covered: %s", resolved_topic)
            except Exception as exc:
                logger.warning("[DIAGNOSTIC] Practice tool memory lookup failed: %s", exc)

        if not resolved_level:
            resolved_level = "beginner"

        # 1. Attempt Primary Source: External German Language Learning API
        result = await asyncio.to_thread(_fetch_external_german_practice_sync, resolved_level, resolved_topic, resolved_type)
        if result:
            logger.info("German practice retrieved successfully from external API")
            return json.dumps(result, ensure_ascii=False)

        # 2. External API failed or unavailable -> Fallback to local dataset
        logger.info("External learning API unavailable; using local fallback")
        fallback_result = _load_local_fallback_exercise(resolved_level, resolved_topic, resolved_type)
        if fallback_result:
            return json.dumps(fallback_result, ensure_ascii=False)

        # 3. Both sources unavailable
        logger.error("[DIAGNOSTIC] Both external API and local fallback dataset failed to load an exercise!")
        return json.dumps({
            "status": "error",
            "message": "I'm unable to load an exercise right now. Please try again in a moment."
        })

    @function_tool(
        description=(
            "Create an escalation request and email a human teacher for help. "
            "Use this tool ONLY when the learner is frustrated/upset and explicitly requests a teacher, "
            "or asks for something requiring human teacher judgment or intervention. "
            "CRITICAL REQUIREMENT: You MUST ask the learner for permission FIRST and receive explicit YES consent BEFORE calling this tool. "
            "Set consent_confirmed=True ONLY after the learner explicitly agrees."
        )
    )
    async def create_escalation(
        self,
        context: RunContext,
        reason: str,
        summary: str,
        what_was_checked: str,
        urgency: str = "medium",
        consent_confirmed: bool = False,
        language: str = "English",
        preferred_follow_up: str = "Email",
    ) -> str:
        """Create and submit an escalation request to a human teacher via email."""
        logger.info("[ESCALATION] Escalation requested for learner_id=%s | urgency=%s", self._user_id, urgency)

        if not consent_confirmed:
            logger.warning("[ESCALATION] Learner declined consent for learner_id=%s", self._user_id)
            return (
                "Escalation cancelled: Learner consent was not confirmed. "
                "You MUST ask the learner for permission and get explicit YES consent before calling create_escalation."
            )

        logger.info("[ESCALATION] Consent confirmed for learner_id=%s", self._user_id)

        valid_urgency = urgency.lower() if urgency.lower() in ("low", "medium", "high") else "medium"

        if ESCALATION_AVAILABLE:
            safe_reason = sanitize_text(reason)
            safe_summary = sanitize_text(summary)
            safe_checked = sanitize_text(what_was_checked)
            ref_id = generate_reference_id()
        else:
            safe_reason = reason
            safe_summary = summary
            safe_checked = what_was_checked
            ref_id = f"DM-2026-{uuid.uuid4().hex[:6].upper()}"

        logger.info("[ESCALATION] Creating request %s for learner_id=%s", ref_id, self._user_id)

        if not ESCALATION_AVAILABLE:
            logger.error("[ESCALATION] Escalation module not available.")
            return "Escalation module is not available."

        success, email_err = await send_escalation_email(
            reference_id=ref_id,
            learner_id=self._user_id,
            summary=safe_summary,
            what_was_checked=safe_checked,
            urgency=valid_urgency,
            language=language,
            preferred_follow_up=preferred_follow_up,
        )

        if not success:
            logger.error("[ESCALATION] Failed to send email for request %s: %s", ref_id, email_err)
            await save_escalation_db(
                reference_id=ref_id,
                learner_id=self._user_id,
                reason=safe_reason,
                summary=safe_summary,
                what_was_checked=safe_checked,
                urgency=valid_urgency,
                language=language,
                preferred_follow_up=preferred_follow_up,
                status="failed_email",
            )
            return (
                f"EMAIL DELIVERY FAILED ({email_err}). "
                "CRITICAL INSTRUCTION FOR ASSISTANT: The escalation email COULD NOT BE DELIVERED due to a technical delivery error. "
                "You MUST tell the learner honestly in their current conversation language that your request could not be sent right now due to a technical delivery issue. "
                "Do NOT give the learner a reference ID! Do NOT claim that a teacher was notified or that an escalation was sent! "
                "Provide an honest fallback, e.g. offer to continue helping them directly or suggest trying again later."
            )

        logger.info("[ESCALATION] Email sent successfully for request %s", ref_id)

        await save_escalation_db(
            reference_id=ref_id,
            learner_id=self._user_id,
            reason=safe_reason,
            summary=safe_summary,
            what_was_checked=safe_checked,
            urgency=valid_urgency,
            language=language,
            preferred_follow_up=preferred_follow_up,
            status="open",
        )

        return (
            f"Escalation request {ref_id} created and sent successfully to the human teacher. "
            f"Tell the learner their reference ID is {ref_id} and explain that a teacher can review it "
            "and follow up through the configured support process."
        )


# ---------------------------------------------------------------------------
# LiveKit server setup
# ---------------------------------------------------------------------------

server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


async def _get_learner_id(ctx: JobContext) -> str:
    """Derive a stable, authenticated learner ID for this session."""
    if ctx.job and ctx.job.metadata:
        try:
            job_meta = json.loads(ctx.job.metadata)
            if isinstance(job_meta, dict):
                lid = job_meta.get("learner_id", "").strip()
                if lid:
                    logger.info("[DIAGNOSTIC] Authenticated learner_id from job metadata: %s", lid)
                    return lid
        except Exception:
            if ctx.job.metadata.strip() and not ctx.job.metadata.startswith("{"):
                lid = ctx.job.metadata.strip()
                logger.info("[DIAGNOSTIC] Authenticated learner_id from raw job metadata: %s", lid)
                return lid

    try:
        raw_meta = ctx.room.metadata or (ctx.job.room.metadata if ctx.job and ctx.job.room else None) or "{}"
        metadata = json.loads(raw_meta)
        if isinstance(metadata, dict):
            learner_id = metadata.get("learner_id", "").strip()
            if learner_id:
                logger.info("[DIAGNOSTIC] Authenticated learner_id from room metadata: %s", learner_id)
                return learner_id
    except Exception:
        pass

    for attempt in range(15):
        for participant in ctx.room.remote_participants.values():
            if participant.metadata:
                try:
                    p_meta = json.loads(participant.metadata)
                    if isinstance(p_meta, dict):
                        p_learner_id = p_meta.get("learner_id", "").strip()
                        if p_learner_id:
                            logger.info("[DIAGNOSTIC] Authenticated learner_id from participant metadata: %s", p_learner_id)
                            return p_learner_id
                except Exception:
                    pass

            if participant.identity:
                pid = participant.identity.strip()
                if pid.startswith("google_"):
                    p_learner_id = pid[len("google_"):].strip()
                    if p_learner_id:
                        logger.info("[DIAGNOSTIC] Authenticated learner_id from participant identity: %s", p_learner_id)
                        return p_learner_id
                elif pid and pid != "agent" and not pid.startswith("agent_"):
                    logger.info("[DIAGNOSTIC] Authenticated learner_id from participant identity: %s", pid)
                    return pid

        await asyncio.sleep(0.5)

    logger.error(
        "[DIAGNOSTIC] ERROR: No authenticated learner_id found in room metadata or participant metadata/identity!"
    )
    fallback_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, ctx.room.name or "default"))
    logger.warning(
        "[DIAGNOSTIC] Using UNAUTHENTICATED room-name fallback learner_id: %s.",
        fallback_id,
    )
    return fallback_id



def _extract_sip_user(sip_uri: str) -> str:
    """
    Extract only the SIP user or phone number from a SIP URI.
    LiveKit's CreateSIPParticipant API expects `sip_call_to` to be a user or phone number,
    not a full SIP URI (e.g. 'sip:justtcocoo@sip.linphone.org' -> 'justtcocoo').
    """
    target = sip_uri.strip()
    if target.startswith("sip:"):
        target = target[4:]
    if "@" in target:
        target = target.split("@")[0]
    return target


# Outbound-specific addition to the base system prompt.
# This block is appended when the agent is operating in outbound mode.
_OUTBOUND_GREETING_INSTRUCTIONS = """\
---
OUTBOUND CALL BEHAVIOUR — CRITICAL:

This is an OUTBOUND call made by DeutschMate to the learner.
The learner did NOT initiate this call.

When the call connects and the participant joins, you MUST speak FIRST.
Your very first words must clearly state:
  1. WHO is calling (DeutschMate, an AI German tutor)
  2. WHY you are calling (their daily German practice session)
  3. That they can hang up / end the call at any time

Use a natural, concise opening such as:
  "Hallo! This is DeutschMate, your AI German tutor. I'm calling for your
   daily German practice session. You can hang up anytime if you'd like to stop.
   Are you ready to practice?"

Do NOT wait for the learner to speak first.
Do NOT sound like a deceptive human caller.
After the introduction, proceed with the normal German practice session.

If the learner did not answer and you reach voicemail / an automated system:
  - Do NOT leave a message.
  - Call the `end_call` tool immediately.

If the learner asks to end the call, or says goodbye:
  - Acknowledge politely, then call the `end_call` tool.
"""


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # 1. Determine if this job is an outbound practice call based on dispatch metadata
    call_type: str = ""
    sip_uri: str = ""
    if ctx.job and ctx.job.metadata:
        try:
            meta = json.loads(ctx.job.metadata)
            if isinstance(meta, dict):
                call_type = meta.get("call_type", "").strip()
                sip_uri = meta.get("sip_uri", "").strip()
        except Exception:
            pass

    is_outbound = (call_type == "daily_german_practice") or bool(sip_uri)

    # 2. Connect to the LiveKit room & resolve learner memory
    await ctx.connect()

    learner_id = await _get_learner_id(ctx)
    logger.info("[DIAGNOSTIC] learner_id received by agent: %s", learner_id)

    existing_memory: dict | None = None
    if MEMORY_AVAILABLE:
        try:
            existing_memory = await lookup_user(learner_id)
        except Exception as exc:
            logger.error("[DIAGNOSTIC] Memory lookup failed at startup: %s", type(exc).__name__)

    if existing_memory:
        logger.info("[DIAGNOSTIC] memory context injected: YES")
    else:
        logger.info("[DIAGNOSTIC] memory context injected: NO")

    # 3. Construct system prompt with memory context (+ outbound greeting instructions if outbound)
    base_prompt = _build_system_prompt(existing_memory)
    system_prompt = base_prompt + _OUTBOUND_GREETING_INSTRUCTIONS if is_outbound else base_prompt

    # 4. Handle Outbound Session Flow (Day 6)
    if is_outbound:
        logger.info("[OUTBOUND] Outbound practice call detected | room=%s", ctx.room.name)
        if not SIP_OUTBOUND_TRUNK_ID:
            logger.error(
                "[OUTBOUND] SIP_OUTBOUND_TRUNK_ID is not set. "
                "Configure it in backend/.env.local and restart the agent."
            )
            ctx.shutdown()
            return

        if not sip_uri:
            logger.error(
                "[OUTBOUND] No 'sip_uri' found in job metadata. "
                "Pass --sip-uri when triggering the call via outbound_call.py."
            )
            ctx.shutdown()
            return

        logger.info("[OUTBOUND] Dialing SIP target: %s", sip_uri)
        sip_user = _extract_sip_user(sip_uri)
        participant_identity = sip_uri

        try:
            logger.info(
                "[OUTBOUND] Initiating SIP call to user '%s' (URI: %s) via trunk %s",
                sip_user,
                sip_uri,
                SIP_OUTBOUND_TRUNK_ID[:8] + "...",
            )
            await ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=ctx.room.name,
                    sip_trunk_id=SIP_OUTBOUND_TRUNK_ID,
                    sip_call_to=sip_user,
                    participant_identity=participant_identity,
                    participant_name="DeutschMate Learner",
                    wait_until_answered=True,
                )
            )
            logger.info("[OUTBOUND] Call answered by %s", sip_uri)

        except api.TwirpError as exc:
            sip_code = exc.metadata.get("sip_status_code", "unknown")
            sip_status = exc.metadata.get("sip_status", "")
            logger.error(
                "[OUTBOUND] SIP call failed | SIP status: %s %s | details: %s",
                sip_code,
                sip_status,
                exc.message,
            )
            if sip_code in ("486", "600"):
                logger.warning("[OUTBOUND] Learner is busy (SIP %s).", sip_code)
            elif sip_code in ("408", "480", "487"):
                logger.warning("[OUTBOUND] Call not answered or timed out (SIP %s).", sip_code)
            elif sip_code in ("404", "410"):
                logger.warning("[OUTBOUND] SIP URI not found (SIP %s). Check Linphone registration.", sip_code)
            elif sip_code == "603":
                logger.warning("[OUTBOUND] Learner declined the call (SIP 603).")
            else:
                logger.error("[OUTBOUND] Unexpected SIP error (SIP %s).", sip_code)
            ctx.shutdown()
            return

        except Exception as exc:
            logger.error(
                "[OUTBOUND] Unexpected error while creating SIP participant [%s]: %s",
                type(exc).__name__,
                exc,
            )
            ctx.shutdown()
            return

        try:
            participant = await ctx.wait_for_participant(identity=participant_identity)
            logger.info("[OUTBOUND] Participant joined: %s", participant.identity)
        except asyncio.TimeoutError:
            logger.error("[OUTBOUND] Participant did not join within timeout after answering.")
            ctx.shutdown()
            return

        session = AgentSession(
            stt=deepgram.STT(model="nova-3", language="multi"),
            llm=google.LLM(model="gemini-3.5-flash-lite"),
            tts=murf.TTS(
                voice="Pooja",
                style="Conversation",
                tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                text_pacing=True,
            ),
            turn_detection=MultilingualModel(),
            vad=ctx.proc.userdata["vad"],
            preemptive_generation=True,
        )

        agent = Assistant(system_prompt=system_prompt, user_id=learner_id)

        await session.start(
            agent=agent,
            room=ctx.room,
            room_options=room_io.RoomOptions(
                audio_input=room_io.AudioInputOptions(
                    noise_cancellation=noise_cancellation.BVCTelephony(),
                ),
            ),
        )

        logger.info("[OUTBOUND] Session active after participant join — triggering first greeting.")
        await session.generate_reply()
        return

    # 5. Handle Normal Browser Session Flow
    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=google.LLM(
            model="gemini-3.5-flash-lite",
        ),
        tts=murf.TTS(
            voice="Anisha", 
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    await session.start(
        agent=Assistant(system_prompt=system_prompt, user_id=learner_id),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind
                    == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )


if __name__ == "__main__":
    cli.run_app(server)

