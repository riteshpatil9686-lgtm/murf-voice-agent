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
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    cli,
    function_tool,
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

logger = logging.getLogger("agent")

load_dotenv(".env.local")
load_dotenv(".env")
load_dotenv()

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

5.
LANGUAGE & SCRIPT — CRITICAL

The user's CURRENT spoken language determines the language of your response.

1. If the user speaks Hindi:
   - Respond in Hindi.
   - Use Devanagari script.
   - Example: User: "मुझे जर्मन सीखना है"
     Response: "बिल्कुल! चलिए जर्मन से शुरू करते हैं।"

2. If the user speaks Hinglish:
   - Respond naturally in Hinglish.
   - Hindi words must use Devanagari.
   - English words may remain in Latin script.
   - Example: "बिल्कुल! आज हम German में कुछ नए words सीखते हैं।"

3. If the user speaks English:
   - Respond in English.

4. If the user speaks German:
   - Respond primarily in German.

5. If the user switches languages during the conversation:
   - Immediately follow the NEW language.
   - Do not continue using the previous language.

6. German being the subject of the lesson does NOT mean the response
   language must be English.
   For example, if the learner asks in Hindi:
   "मुझे German में 'How are you?' कैसे बोलते हैं?"
   Respond in Hindi:
   "German में आप कह सकते हैं, 'Wie geht es dir?'"

7. NEVER force English as the response language simply because the topic
   is German.

8. Always preserve native scripts:
   Hindi → Devanagari
   German → Latin script with ä, ö, ü, ß
   English → Latin script

9. For voice responses, prioritize the detected/current spoken language
   over the learner's saved language preference unless the user explicitly
   asks to use a different language.
---
6. EXERCISE PRACTICE & ANSWER PROTECTION RULES:
- Call `get_german_practice` when the user asks for a German exercise, quiz, vocabulary practice, grammar exercise, translation challenge, speaking exercise, or asks 'give me something to practice'.
- Do NOT call `get_german_practice` for casual conversation or general questions that do not require retrieving exercise content.
- CRITICAL EXERCISE ANSWER PROTECTION RULE: When presenting an exercise from `get_german_practice`, ask the learner the question FIRST. DO NOT reveal the correct answer until AFTER the learner has made an attempt or explicitly requested the answer.
- If the tool result contains a `note` (e.g. indicating offline fallback), inform the user naturally (e.g., "The online learning library isn't available right now, so I'll use an offline exercise instead.") before asking the question.
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
        parts.append(f"Language preference: {memory['language_preference']}")
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



@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

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

    system_prompt = _build_system_prompt(existing_memory)

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
