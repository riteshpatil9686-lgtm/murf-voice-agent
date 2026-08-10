# DeutschMate 🇩🇪

> *"Language is learned in conversation."*

**DeutschMate** is a real-time multilingual AI voice tutor designed to help learners practice German through natural, interactive voice conversations. Built for the **VoiceForBharat** challenge (*10 Days of Voice Agents*), DeutschMate combines low-latency real-time speech processing, persistent learner memory, and dynamic language-learning exercise retrieval into an intuitive, accessible voice experience.

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

---

## 🏗️ Architecture

```
                                    +-----------------------+
                                    |    Learner (User)     |
                                    +-----------+-----------+
                                                |
                                        (Audio / WebRTC)
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
                               | (src/agent.py + src/memory.py)  |
                               +----------------+----------------+
                                                |
        +-------------------+-------------------+-------------------+-------------------+
        |                   |                   |                   |                   |
        v                   v                   v                   v                   v
+---------------+   +---------------+   +---------------+   +---------------+   +---------------+
| Deepgram      |   | Google Gemini |   | Murf Falcon   |   | PostgreSQL    |   | German        |
| Nova-3        |   | 3.5 Flash-Lite|   | TTS           |   | Database      |   | Practice Tool |
| (Speech-to-   |   | (Language &   |   | (Voice        |   | (Learner      |   | (Learning     |
| Text)         |   | Reasoning)    |   | Synthesis)    |   | Memory)       |   | Data Engine)  |
+---------------+   +---------------+   +---------------+   +---------------+   +-------+-------+
                                                                                        |
                                                                        +---------------+---------------+
                                                                        |                               |
                                                                        v                               v
                                                              +-------------------+           +-------------------+
                                                              | External German   |           | Local JSON        |
                                                              | Learning API      |  (fail)   | Fallback Dataset  |
                                                              | (onrender.com)    +---------->| (75 Curated       |
                                                              | (Primary)         |           | Exercises)        |
                                                              +-------------------+           +-------------------+
```

### Typical Interaction Flow
1. **Connection & Identity**: The learner signs in via Google OAuth. The Next.js frontend passes the authenticated `sub` ID as metadata over LiveKit.
2. **Memory Ingestion**: The agent queries PostgreSQL for existing learner records (level, mistakes, topics) and injects this context into the active session.
3. **Voice Processing**: User audio is streamed via WebRTC to LiveKit, converted to text via Deepgram Nova-3, and processed by Google Gemini 3.5 Flash-Lite.
4. **Tool Execution**: When an exercise is requested, `get_german_practice()` calls the external API (or local JSON fallback if offline) and presents the question.
5. **Speech Response**: The response text is synthesized into natural audio using Murf Falcon TTS (Voice: *Anisha*) and streamed back to the learner.

---

## 🔄 Exercise Retrieval Fallback Logic

```
 Learner requests practice exercise
                │
                ▼
      get_german_practice()
                │
                ▼
   Attempt External German API
 (https://german-language.onrender.com)
                │
        ┌───────┴───────┐
        │               │
  [ API Success ]  [ API Fail / Timeout ]
        │               │
        ▼               ▼
  Return API      Read Hand-Curated
   Exercise        Local JSON File
                        │
                ┌───────┴───────┐
                │               │
          [ JSON Success ]  [ Read Error ]
                │               │
                ▼               ▼
          Return Local    Return Graceful
            Exercise       Error Message
```

---

## 🛠️ Tech Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend** | Next.js 15, React 19, TypeScript, Tailwind CSS | Liquid-glass user interface & auth flow |
| **Backend Agent** | Python 3.10+, `livekit-agents` SDK | Async agent orchestration & tool calls |
| **Transport** | LiveKit WebRTC Server | Sub-second real-time audio streaming |
| **Speech-to-Text (STT)** | Deepgram Nova-3 | Multilingual speech transcription |
| **Language Model (LLM)** | Google Gemini 3.5 Flash-Lite | Context reasoning, tutoring logic & tool execution |
| **Text-to-Speech (TTS)** | Murf Falcon (`Anisha` voice profile) | Ultra-low latency voice synthesis |
| **Database** | PostgreSQL | Persistent learner memory and profile storage |
| **Authentication** | Google OAuth 2.0 (NextAuth.js) | Stable user identity management |
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

---

## 📊 Day 5 Data Source Disclosure

In compliance with challenge transparency requirements, DeutschMate utilizes a multi-tiered data retrieval strategy for German language exercises:

1. **Primary Source — External API**:
   - **Service**: [German Language Learning API](https://german-language.onrender.com)
   - **Capabilities**: Dynamically queries vocabulary (`/vocab`), grammar rules (`/grammar`), and sentence translations (`/sentences/random`).
   - **Security**: Authenticated via `GERMAN_API_KEY` header.

2. **Fallback Source — Local Curated Dataset**:
   - **Path**: `backend/data/german_exercises.json`
   - **Details**: A hand-curated dataset containing **75 exercises** categorized by CEFR levels (**30 A1, 20 A2, 15 B1, 10 B2**) covering 15 diverse topics (travel, work, grammar, daily life, directions, etc.).
   - **Usage**: Automatically engaged if the external API is unreachable, rate-limited, or returns a network error, ensuring uninterrupted learning sessions without extra LLM overhead.

---

## 📁 Project Structure

```
murf-voice-agent/
├── backend/                        # Python Voice Agent Application
│   ├── data/
│   │   └── german_exercises.json   # Hand-curated local fallback dataset (75 exercises)
│   ├── src/
│   │   ├── agent.py                # Main agent logic, system prompt & tool handlers
│   │   ├── memory.py               # Learner memory module & PostgreSQL CRUD operations
│   │   ├── db.py                   # PostgreSQL connection pool manager
│   │   └── migrate.py              # Database schema migration script
│   ├── tests/
│   │   └── test_practice.py        # Integration tests for external API & fallback logic
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
└── README.md                       # Project documentation
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

# PostgreSQL Memory Store
DATABASE_URL=postgresql://postgres:password@localhost:5432/deutschmate

# German Learning API Key
GERMAN_API_KEY=demo-key-12345
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
- **LiveKit Server**: Executable or LiveKit Cloud account

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
Ensure PostgreSQL is running, then run the database migration:

```bash
cd backend
uv run python src/migrate.py
```

### Step 3: Run the Application

Run the following services in **three separate terminals**:

#### Terminal 1 — LiveKit Server (Local Dev)
```powershell
.\livekit-server.exe --dev
```
*(Note: `livekit-server.exe` is a local development binary and is excluded from version control).*

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

Open **http://localhost:3000** in your browser, sign in with Google, and click **Start Talking** to begin practicing German!

---

## 🧪 Testing & Verification

### Automated Backend Test
Run the test suite to verify the German practice tool, external API connectivity, and local JSON fallback:

```bash
cd backend
uv run python tests/test_practice.py
```

### Manual Verification Checklist
- [x] **Google Authentication**: Sign in and verify your Google profile email/picture appear in the UI.
- [x] **Voice Pipeline**: Connect to the agent and confirm audio response playback via Murf Falcon.
- [x] **Multilingual Code-Switching**: Speak in Hindi/Hinglish to verify Devanagari Hindi responses, and speak in German to verify correct diacritic usage (`ä`, `ö`, `ü`, `ß`).
- [x] **Practice Tool Execution**: Ask *"Give me a German exercise"* and confirm `get_german_practice()` fetches a question without revealing the answer upfront.
- [x] **Memory Persistence**: Ask the agent to save your level (e.g., *"Set my German level to A2"*), end the call, sign in again, and verify the agent recalls your level.

---

## 🙌 Built on the Murf AI Starter

DeutschMate was developed starting from the open-source **[Murf AI LiveKit Voice Agent Starter](https://github.com/murf-ai/murf-livekit-starter)**. 

Special thanks to **Murf AI** and **LiveKit** for providing the high-speed text-to-speech engine and real-time audio transport foundation that made DeutschMate possible during the **VoiceForBharat** challenge!

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
