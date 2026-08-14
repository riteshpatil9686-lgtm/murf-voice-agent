# DeutschMate 🇩🇪

> *"Language is learned in conversation."*

**DeutschMate** is a real-time multilingual AI voice tutor designed to help learners practice German through natural, interactive voice conversations. Built for the **VoiceForBharat** challenge (*10 Days of Voice Agents*), DeutschMate combines low-latency real-time speech processing, persistent learner memory, dynamic language-learning exercise retrieval, human teacher escalation, PostgreSQL call analytics, and specialist agent handoff into an intuitive, accessible voice experience.

Powered by Murf Falcon, the fastest TTS API, the experience is smooth, natural, and voice-first.

---

## 🌟 Key Features

### 1. 🎙️ Real-Time Multilingual Voice Conversations
- **Live Voice Interaction**: Seamless bidirectional streaming via LiveKit Agents with ultra-fast speech synthesis.
- **Dynamic Multilingual Code-Switching**: Speaks and responds fluently in **German**, **English**, **Hindi**, and **Hinglish**, matching the learner's spoken language.
- **Native Script Fidelity**: Generates Devanagari script for Hindi responses and handles native German diacritics (`ä`, `ö`, `ü`, `ß`).

### 2. 🧠 Persistent Learner Memory
- **Stable OAuth Identity**: Uses authenticated **Google Account (`sub` ID)** as the unique learner identifier, ensuring different accounts with identical display names maintain separate memory profiles.
- **PostgreSQL Context Store**: Remembers learner levels (A1–B2), primary goals, topics covered, and recurring grammar/pronunciation mistakes across sessions.
- **Privacy & Consent Gate**: Explicitly requests user consent before persisting memory records, storing only relevant learning insights—never raw conversation audio or transcripts.

### 3. 📚 Dynamic German Practice & Tool Integration
- **`get_german_practice()` Function Tool**: Autonomously triggered when a learner asks for quizzes, vocabulary drills, grammar tasks, or translation challenges.
- **Memory-Driven Retrieval**: Uses stored learner memory to fill in missing level or topic preferences automatically.
- **Answer Protection**: Delivers exercise questions first and withholds answers until the learner attempts the response or requests help.

### 4. ⚡ Resilient Learning Data Engine
- **Primary Source (External API)**: Connects to the [German Language Learning API](https://german-language.onrender.com) for real-time vocabulary, grammar rules, and sentence translation practice.
- **Local Fallback Dataset**: If the external API times out or is unavailable, the agent seamlessly switches to a hand-curated offline dataset (`backend/data/german_exercises.json`) containing 75 level-structured exercises across CEFR levels A1, A2, B1, and B2.

### 5. 🎨 Modern Liquid-Glass Frontend
- **Real-Time Visual Agent States**: Clear state indication across 5 phases: `Ready`, `Connecting`, `Listening`, `Speaking`, and `Call Ended`.
- **User Experience**: Smooth visualizer animations, intuitive microphone permission handling, one-click reconnection, and Google Sign-In identity integration.

### 6. 📞 Outbound German Practice Calls (Day 6)
- **SIP Outbound Calling**: DeutschMate initiates outbound calls to a learner's Linphone SIP softphone for daily practice sessions.
- **Transparent Agent Greeting**: Agent speaks first upon pickup, clearly identifying itself and the call purpose, allowing the learner to disconnect anytime.
- **Unified Identity**: Learner identity (`sub` ID) passed via dispatch metadata so the outbound session loads the exact same PostgreSQL memory profile.

### 7. 🆘 Human Teacher Escalation (Day 7)
- **Distress & Request Recognition**: Automatically detects learner distress/anxiety or explicit requests for human teacher assistance.
- **Pre-Call Consent Flow**: Acknowledges feelings in the learner's spoken language, explains what will be shared, and explicitly asks permission before generating an escalation request.
- **Secure Email Summaries**: Creates a sanitized request summary with a unique reference ID (e.g. `DM-2026-XXXXXX`), emails a human teacher via SMTP, records the entry in PostgreSQL, and provides honest next steps (or an honest fallback if delivery fails).

### 8. 📊 Call Analytics & Dashboard (Day 8)
- **Exercise-Based Success Metric**: Defines a successful DeutschMate session as one where the learner successfully completes a German practice exercise (`mark_exercise_complete`).
- **PostgreSQL Persistence**: Automatically records call outcomes (`success` or `failed`) per session in `call_analytics` table upon room teardown.
- **Localhost Dashboard**: Lightweight HTTP dashboard running on **`http://localhost:8888`** showing Total Calls, Successful Calls, Failed Calls, and Success Rate (%) using real call data without exposing transcripts or private learner information.

### 9. 👔 German Job Interview Coach Specialist & Handoff (Day 9)
- **Dedicated Specialist Agent**: Introduces `GermanJobInterviewCoach`, a separate agent class focused exclusively on mock German job interviews, corrections, and interview feedback.
- **Distinct Murf TTS Voices**: Main DeutschMate agent uses Murf voice **`Pooja`** (female); Specialist agent uses Murf voice **`Samar`** (male).
- **Context-Aware Handoff**: Main agent recognizes interview practice requests, announces the transition (*"Absolutely. I'll connect you with our German Job Interview Coach."*), extracts target role/date details, and hands off the session using LiveKit's native agent update mechanism (`handoff_to_job_interview_coach`). The specialist receives full conversation history and opens directly with a tailored interview question without asking the learner to repeat details.

---

## 🏗️ Architecture

```
                                    +-----------------------+
                                    |    Learner (User)     |
                                    +-----------+-----------+
                                                |
                                        (Audio / WebRTC / SIP)
                                                v
                                  +---------------------------+
                                  |   DeutschMate Frontend    |
                                  |   (Next.js + NextAuth)    |
                                  +-------------+-------------+
                                                |
                                                v
                                    +-----------------------+
                                    |    LiveKit Server     |
                                    |  (Real-time Transport)|
                                    +-----------+-----------+
                                                |
                                                v
                                +---------------------------------+
                                |   Python Voice Agent Engine     |
                                |       (src/agent.py)            |
                                +---------------+-----------------+
                                                |
              +---------------------------------+---------------------------------+
              |                                                                   |
              v                                                                   v
  +-----------------------+                                           +-----------------------+
  |   Main Agent          |                                           | Specialist Agent      |
  |  (DeutschMate)        |=====[ handoff_to_job_interview_coach ]===>| (German Job Interview |
  |  Voice: Pooja         |                                           |  Coach)               |
  |  General Practice     |                                           |  Voice: Samar         |
  +-----------+-----------+                                           +-----------+-----------+
              |                                                                   |
              +---------------------------------+---------------------------------+
                                                |
        +-------------------+-------------------+-------------------+-------------------+
        |                   |                   |                   |                   |
        v                   v                   v                   v                   v
+---------------+   +---------------+   +---------------+   +---------------+   +---------------+
| Deepgram      |   | Google Gemini |   | Murf Falcon   |   | PostgreSQL    |   | German        |
| Nova-3        |   | 3.5 Flash-Lite|   | TTS           |   | Database      |   | Practice Tool |
| (Speech-to-   |   | (Language &   |   | (Pooja/Samar) |   | (Memory,      |   | (Learning     |
| Text)         |   | Reasoning)    |   |               |   | Escalations,  |   | Data Engine)  |
|               |   |               |   |               |   | Analytics)    |   |               |
+---------------+   +---------------+   +---------------+   +-------+-------+   +-------+-------+
                                                                        |                   |
                                                                        v                   v
                                                                +---------------+   +---------------+
                                                                | Dashboard     |   | External API  |
                                                                | Server        |   | / Fallback    |
                                                                | (port 8888)   |   | Exercises     |
                                                                +---------------+   +---------------+
```

### Typical Interaction Flow
1. **Connection & Identity**: The learner signs in via Google OAuth. The Next.js frontend passes the authenticated `sub` ID as metadata over LiveKit.
2. **Memory Ingestion**: The agent queries PostgreSQL for existing learner records (level, mistakes, topics) and injects this context into the active session.
3. **Voice Processing**: User audio is streamed via WebRTC to LiveKit, converted to text via Deepgram Nova-3, and processed by Google Gemini 3.5 Flash-Lite.
4. **General Practice / Tool Execution**: When an exercise is requested, `get_german_practice()` calls the external API (or local JSON fallback if offline) and presents the question.
5. **Specialist Handoff**: If the user requests job interview practice, the main agent announces the switch and invokes `handoff_to_job_interview_coach`. The session transitions to `GermanJobInterviewCoach` using Murf voice **Samar**, preserving conversation history and target job role details.
6. **Analytics Recording**: Upon session completion, the agent automatically logs the call outcome (`success` if an exercise was completed, `failed` otherwise) in `call_analytics`.

---

## 🛠️ Tech Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend** | Next.js 15, React 19, TypeScript, Tailwind CSS | Liquid-glass user interface & auth flow |
| **Backend Agent** | Python 3.10+, `livekit-agents` SDK | Async agent orchestration, multi-agent handoff & tool calls |
| **Transport** | LiveKit WebRTC Server & LiveKit SIP Trunk | Sub-second real-time audio streaming & SIP outbound calls |
| **Speech-to-Text (STT)** | Deepgram Nova-3 | Multilingual speech transcription |
| **Language Model (LLM)** | Google Gemini 3.5 Flash-Lite | Context reasoning, tutoring logic, escalation & tool execution |
| **Text-to-Speech (TTS)** | Murf Falcon (`Pooja` main, `Samar` specialist) | Ultra-low latency voice synthesis with distinct agent voices |
| **Database** | PostgreSQL (`asyncpg`) | Persistent learner memory, escalation records & call analytics |
| **Analytics Dashboard** | Python HTTP Server (`src/dashboard.py`) | Real-time analytics dashboard on `http://localhost:8888` |
| **Authentication** | Google OAuth 2.0 (NextAuth.js) | Stable user identity management via `sub` ID |
| **External API** | German Language Learning API | Online exercises, grammar rules, & vocabulary |
| **Fallback Data** | Curated JSON (`german_exercises.json`) | Reliable offline exercise dataset (75 exercises) |
| **Package Managers** | `uv` (Python), `pnpm` (Node.js) | High-performance dependency management |

---

## 🚀 10 Days of Voice Agents — Progress

- [x] **Day 1 — First Conversation**: Implemented the core real-time voice pipeline using LiveKit Agents, Deepgram STT, Gemini LLM, and Murf Falcon TTS.
- [x] **Day 2 — Improving the Voice Experience**: Optimized turn-taking, prompt instructions, and audio streaming parameters to minimize latency.
- [x] **Day 3 — Building the DeutschMate Frontend**: Designed a liquid-glass UI with 5 agent states (`Ready`, `Connecting`, `Listening`, `Speaking`, `Call ended`), microphone controls, and custom branding.
- [x] **Day 4 — Giving DeutschMate Memory**: Integrated PostgreSQL and Google OAuth to establish stable `sub`-based learner profiles, supporting consent-gated memory storage across sessions.
- [x] **Day 5 — Giving DeutschMate Access to Learning Data**: Built the `get_german_practice()` tool with primary external API fetching, level/topic matching, and an expanded 75-exercise local JSON fallback engine.
- [x] **Day 6 — Outbound Calling (Learning & Literacy Track)**: Added Daily German Practice Call capability. DeutschMate calls the learner's Linphone SIP address, speaks first with a transparent introduction, then conducts a full German practice session using the complete Day 4/5 pipeline.
- [x] **Day 7 — Human Teacher Escalation**: Added human-help escalation capability (`create_escalation` tool). Recognizes learner distress/requests, requests permission before sharing info, generates unique reference IDs (e.g. `DM-2026-XXXXXX`), emails summary to human teacher, stores entry in PostgreSQL, and provides honest next steps.
- [x] **Day 8 — Call Analytics**: Added PostgreSQL-backed call analytics (`call_analytics` table). Defines a successful call as successfully completing a German exercise. Tracks outcomes (`success`/`failed`), and provides a localhost dashboard on `http://localhost:8888` showing Total Calls, Successful Calls, Failed Calls, and Success Rate using real call data.
- [x] **Day 9 — German Job Interview Coach Specialist Agent**: Created a dedicated specialist agent (`GermanJobInterviewCoach`) with Murf voice **Samar**. Main agent (voice **Pooja**) detects interview requests, announces handoff, extracts target role/date, and transfers session with full conversation history preserved.
- [ ] **Day 10 — Final Polish & Submission**: Video demonstration, final optimization, and project submission.

---

## 📞 Day 6 — Daily German Practice Call (Outbound via Linphone)

> **VoiceForBharat Challenge — Learning & Literacy Track**
> DeutschMate calls a learner for a short German practice session using the official Linphone/SIP outbound approach.

### Architecture

```
[outbound_call.py]                   ← You run this script to trigger the call
       │
       │  LiveKit Dispatch API
       │  (CreateAgentDispatch — new room + metadata JSON)
       │
       ▼
[DeutschMate Agent Worker]           ← Already running via `python src/agent.py dev`
(outbound_practice_session entrypoint)
       │
       │  LiveKit SIP Outbound Trunk
       │  (ctx.api.sip.create_sip_participant, wait_until_answered=True)
       │
       ▼
[Linphone App]                       ← Learner's SIP softphone (sip.linphone.org)
       │
       │  Learner answers
       │
       ▼
[DeutschMate Agent speaks FIRST]
  "Hallo! This is DeutschMate, your AI German tutor.
   I'm calling for your daily German practice session.
   You can hang up anytime if you'd like to stop."
       │
       ▼
[Normal German Practice Session]     ← Murf Falcon + Deepgram + Gemini + Memory + Practice Tool
```

### Learner Identity
The outbound call passes the learner's authenticated **Google `sub` ID** as `learner_id` inside the dispatch metadata JSON. The agent's `_get_learner_id()` reads this from `ctx.job.metadata` (highest-priority path), so the **same PostgreSQL memory** is loaded as in a normal web session. No UUID is generated, no phone number is used as identity.

---

## 🆘 Day 7 — Human Teacher Escalation

> **VoiceForBharat Challenge — Support & Escalation**

DeutschMate can recognize when a learner requires assistance from a human teacher and safely escalates requests while respecting learner privacy.

### Escalation Triggers
1. **Learner Distress / Anxiety**: Expressing significant frustration or feeling overwhelmed (e.g., *"I'm very anxious"*, *"Mujhe samajh nahi aa raha hai"*).
2. **Explicit Request for Human Help**: Explicitly requesting a human teacher or grading assistance (e.g., *"Can I talk to a teacher?"*, *"I want a human to review my essay"*).

### Consent Flow & Privacy
- **Pre-Call Consent**: The agent acknowledges feelings, explains what summary will be shared, and explicitly asks permission before creating an escalation.
- **Reference ID**: Generates a tracking ID format `DM-2026-XXXXXX`.
- **Sanitized Email Delivery**: Strips raw transcripts, credentials, or passwords, sending a concise summary to the configured teacher email via SMTP.
- **Honest Feedback**: Informs the learner of their reference ID and next steps, or provides an honest fallback if email delivery fails.

---

## 📊 Day 8 — Call Analytics & Dashboard

> **VoiceForBharat Challenge — Call Analytics**

DeutschMate tracks call performance and learning outcome metrics using PostgreSQL analytics storage and a local dashboard.

### Definition of Success
- **Successful Call**: A session where the learner successfully completes at least one German practice exercise (`mark_exercise_complete`).
- **Failed Call**: A session where the learner disconnects without completing an exercise.

### Dashboard Server
- **URL**: **`http://localhost:8888`**
- **Command**: `uv run python src/dashboard.py`
- **Metrics Displayed**: Total Calls, Successful Calls, Failed Calls, Success Rate (%), and Recent Call History.
- **Data Privacy**: Built strictly on PostgreSQL metadata rows without logging transcript text or audio.

---

## 👔 Day 9 — German Job Interview Coach Specialist & Agent Handoff

> **VoiceForBharat Challenge — Specialized Agents & Agent Handoff**

DeutschMate includes a dedicated specialist agent for German job interview preparation, featuring multi-agent orchestration and dynamic voice switching.

### Specialist Agent (`GermanJobInterviewCoach`)
- **Role**: Helps learners prepare for German-language job interviews, conducts realistic mock interviews, asks targeted questions, corrects German grammar/vocabulary mistakes, and gives constructive interview feedback.
- **Murf Voice**: **`Samar`** (Indian English, male).

### Main Agent (`Assistant`)
- **Role**: Handles general German tutoring, exercises, learner memory, escalation, and outbound calls.
- **Murf Voice**: **`Pooja`** (Indian English, female).

### Handoff Flow
1. Learner requests interview practice (e.g., *"I have an interview next Tuesday for a software engineer position in Germany."*).
2. Main Agent recognizes the interview request, identifies the target role (*software engineer*) and date (*next Tuesday*), and announces:
   *"Absolutely. I'll connect you with our German Job Interview Coach."*
3. Main Agent invokes `handoff_to_job_interview_coach` tool.
4. Active session updates to `GermanJobInterviewCoach` via LiveKit's `context.session.update_agent()`.
5. Murf voice switches seamlessly from **Pooja** to **Samar**.
6. Specialist receives prior conversation history (`chat_ctx`) and target role details, opening directly with a tailored interview question (*"Hi! I'm your German Job Interview Coach. Since you're preparing for a software engineering interview next Tuesday, let's begin with a typical opening question: Erzählen Sie mir bitte etwas über sich."*) without asking the learner to repeat details.

---

## 📁 Project Structure

```
murf-livekit-starter/
├── backend/                        # Python Voice Agent Application
│   ├── data/
│   │   └── german_exercises.json   # Hand-curated local fallback dataset (75 exercises)
│   ├── src/
│   │   ├── agent.py                # Main agent (Assistant), Specialist (GermanJobInterviewCoach) & handoff tools
│   │   ├── analytics.py            # Call analytics recorder (record_call)
│   │   ├── dashboard.py            # Analytics dashboard server (http://localhost:8888)
│   │   ├── memory.py               # Learner memory module & PostgreSQL CRUD operations
│   │   ├── db.py                   # PostgreSQL connection pool manager
│   │   ├── escalation.py           # Human teacher escalation module & SMTP mailer
│   │   ├── migrate.py              # Database schema migration script
│   │   └── outbound_call.py        # Outbound SIP call dispatch script
│   ├── tests/
│   │   ├── test_agent.py           # LLM-judged eval suite (greetings, grounding, safety refusal)
│   │   ├── test_analytics.py       # Call analytics recorder unit tests
│   │   ├── test_day9_handoff.py    # Specialist agent & handoff unit tests
│   │   ├── test_escalation.py      # Human escalation unit tests
│   │   └── test_practice.py        # Practice exercise API & fallback integration tests
│   ├── .env.example                # Backend environment variable template
│   ├── pyproject.toml              # Python project configuration (uv)
│   └── Dockerfile                  # Container deployment configuration
├── frontend/                       # Next.js Frontend Application
│   ├── app/
│   │   ├── api/                    # NextAuth & LiveKit token API routes
│   │   ├── layout.tsx              # Root layout & providers
│   │   └── page.tsx                # Main voice agent interface
│   ├── components/                 # UI components (Agent status, visualizer, auth buttons)
│   ├── auth.ts                     # NextAuth configuration & Google OAuth sub handler
│   ├── app-config.ts               # Application metadata & branding config
│   ├── .env.example                # Frontend environment variable template
│   └── package.json                # Node.js dependencies (pnpm)
├── start_app.ps1                   # Windows startup script
├── start_app.sh                    # Linux/macOS startup script
└── README.md                       # Main project documentation
```

---

## 🔒 Memory & Privacy

- **Explicit Consent**: DeutschMate requires explicit user consent before storing any memory records.
- **Focused Data Collection**: Only learning metadata (CEFR level, target goals, weak topics, common mistakes) is stored.
- **No Audio/Transcript Logging**: Full raw audio streams and transcript histories are never persisted in the database.
- **Account Isolation**: Learner profiles are indexed strictly by authenticated Google OAuth `sub` identifiers. Different accounts sharing the same display name remain completely isolated.

---

## ⚙️ Environment Variables

### Backend (`backend/.env.local`)
```env
# LiveKit Transport
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret

# Speech & Voice AI
MURF_API_KEY=your_murf_api_key
DEEPGRAM_API_KEY=your_deepgram_api_key
GOOGLE_API_KEY=your_google_ai_studio_key

# PostgreSQL Store (Memory, Escalation & Analytics)
DATABASE_URL=postgresql://postgres:password@localhost:5432/deutschmate

# German Learning API Key
GERMAN_API_KEY=demo-key-12345

# Optional: Outbound SIP Trunk ID (Day 6)
SIP_OUTBOUND_TRUNK_ID=ST_your_trunk_id_here

# Optional: Human Escalation SMTP Config (Day 7)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
TEACHER_EMAIL=teacher@example.com
```

### Frontend (`frontend/.env.local`)
```env
# LiveKit Config (Must match backend project)
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret

# Google OAuth Credentials
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret

# NextAuth Session Secret
AUTH_SECRET=your_generated_32_byte_secret
```

---

## 🚀 Setup & Running Locally

### Prerequisites
- **Python**: 3.10 or higher
- **uv**: Fast Python package manager (`pip install uv` or `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`)
- **Node.js**: v18+ & **pnpm**: (`npm install -g pnpm`)
- **PostgreSQL**: Local server or cloud instance (e.g. Neon / Supabase)
- **LiveKit Server**: Local binary or LiveKit Cloud account

### Step 1: Install Dependencies

```bash
# Install backend dependencies
cd backend
uv sync

# Install frontend dependencies
cd ../frontend
pnpm install
```

### Step 2: Initialize Database
Ensure PostgreSQL is running, then run the database migration to set up `learners`, `memory_facts`, `escalations`, and `call_analytics` tables:

```bash
cd backend
uv run python src/migrate.py
```

### Step 3: Run the Application

Run the following services in separate terminals:

#### Terminal 1 — LiveKit Server (Local Dev)
```powershell
.\livekit-server.exe --dev
```

#### Terminal 2 — Backend Voice Agent
```powershell
cd backend
uv run python src/agent.py dev
```

#### Terminal 3 — Next.js Frontend
```powershell
cd frontend
pnpm dev
```

#### Terminal 4 (Optional) — Analytics Dashboard (Day 8)
```powershell
cd backend
uv run python src/dashboard.py
```
Open **`http://localhost:8888`** to view call analytics metrics.

Open **http://localhost:3000** in your browser, sign in with Google, and click **Start Talking** to begin practicing German!

---

## 🧪 Testing & Verification

### Automated Backend Test Suite
Run the full unit and integration test suite (14 tests):

```bash
cd backend
uv run pytest
```

The test suite covers:
- `test_agent.py`: Greetings, grounding, and harmful request safety refusals.
- `test_analytics.py`: `call_analytics` database insertion and query logic.
- `test_day9_handoff.py`: Specialist agent initialization, Samar TTS voice, handoff tool registration, and context preservation.
- `test_escalation.py`: Human teacher escalation triggers, consent checks, and reference ID generation.
- `test_practice.py`: External German API integration and local exercise fallback logic.

### Manual Verification Checklist
- [x] **Google Authentication**: Sign in and verify your Google profile email/picture appear in the UI.
- [x] **Voice Pipeline**: Connect to the agent and confirm audio response playback via Murf Falcon (`Pooja`).
- [x] **Multilingual Code-Switching**: Speak in Hindi/Hinglish to verify Devanagari Hindi responses, and speak in German to verify correct diacritic usage (`ä`, `ö`, `ü`, `ß`).
- [x] **Practice Tool Execution**: Ask *"Give me a German exercise"* and confirm `get_german_practice()` fetches a question without revealing the answer upfront.
- [x] **Memory Persistence**: Ask the agent to save your level (e.g., *"Set my German level to A2"*), end the call, sign in again, and verify the agent recalls your level.
- [x] **Outbound SIP Call (Day 6)**: Trigger an outbound call via `outbound_call.py` to a Linphone address and verify transparent greeting.
- [x] **Human Escalation (Day 7)**: Say *"I'm feeling very overwhelmed, can I talk to a teacher?"*, grant permission, and verify reference ID (`DM-2026-XXXXXX`).
- [x] **Call Analytics (Day 8)**: Complete an exercise, hang up, open `http://localhost:8888`, and verify call outcome recorded as `success`.
- [x] **Job Interview Specialist Handoff (Day 9)**: Say *"I have an interview next Tuesday for a software engineer position in Germany"*, verify Main Agent announcement, voice switch to **Samar**, and opening mock interview question.

---

## 🙌 Built on the Murf AI Starter

DeutschMate was developed starting from the open-source **[Murf AI LiveKit Voice Agent Starter](https://github.com/murf-ai/murf-livekit-starter)**. 

Special thanks to **Murf AI** and **LiveKit** for providing the high-speed text-to-speech engine and real-time audio transport foundation that made DeutschMate possible during the **VoiceForBharat** challenge!

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
