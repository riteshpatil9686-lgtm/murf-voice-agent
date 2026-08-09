"""
agent.py — DeutschMate voice agent with persistent learner memory.

Memory changes (only):
  - Generates / persists an anonymous learner_id stored in the LiveKit
    room metadata (or falls back to ctx.room.name as a stable session key).
  - On session start: calls lookup_user() to greet returning learners.
  - During conversation: tracks name, level, goal, topics, mistakes in state.
  - After gathering information: asks consent before calling save_memory().
  - If DB is unavailable: continues normally; never fabricates memory.

Everything else (LiveKit pipeline, Murf Falcon TTS, Deepgram STT, Gemini LLM,
Silero VAD, MultilingualModel turn detector, noise cancellation) is unchanged.
"""

import asyncio
import json
import logging
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

# ---------------------------------------------------------------------------
# System prompt — memory context is injected dynamically per session.
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
- Give quizzes and speaking exercises.
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
# Agent class with memory tools
# ---------------------------------------------------------------------------

class Assistant(Agent):
    """DeutschMate agent. Holds per-session memory state."""

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
        """Set or update the user's memory consent in PostgreSQL.

        Args:
            consent_granted: Set to True if user gave consent (in any language/affirmative phrase), False if declined.
        """
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
        """Save this learner's progress to the database.

        Args:
            name: The learner's first name.
            language_preference: e.g. "English" or "Hinglish".
            german_level: e.g. "beginner", "intermediate", "advanced".
            learning_goal: e.g. "German for travel".
            topics_covered: List of topics practised this session.
            common_mistakes: List of recurring error patterns.
        """
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


# ---------------------------------------------------------------------------
# LiveKit server setup
# ---------------------------------------------------------------------------

server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


async def _get_learner_id(ctx: JobContext) -> str:
    """Derive a stable, authenticated learner ID for this session.

    Priority:
    1. ctx.job.metadata JSON: {"learner_id": "<google_sub>"}
    2. Room metadata JSON: {"learner_id": "<google_sub>"}
    3. Participant metadata JSON: {"learner_id": "<google_sub>"}
    4. Participant identity: "google_<google_sub>"
    5. Fallback (dev only): UUIDv5 derived from room name.
    """
    # 1. Check job metadata (passed via roomConfig agents[0].metadata)
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

    # 2. Check room metadata
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

    # 3. Check room participants (poll up to 5s if room is empty on start)
    for attempt in range(10):
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

        if ctx.room.remote_participants:
            break
        await asyncio.sleep(0.5)

    # 4. Unauthenticated fallback (dev only)
    logger.error(
        "[DIAGNOSTIC] ERROR: No authenticated learner_id found in room metadata or participant metadata/identity! "
        "Participant token may be missing authenticated session metadata."
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

    # ------------------------------------------------------------------
    # 1. Connect agent to the LiveKit room so room & participant metadata are active
    # ------------------------------------------------------------------
    await ctx.connect()

    # ------------------------------------------------------------------
    # 2. Determine learner ID and load any existing memory BEFORE starting session
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 3. Build the voice pipeline
    # ------------------------------------------------------------------
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


