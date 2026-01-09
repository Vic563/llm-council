# CLAUDE.md - Technical Notes for LLM Council

This file contains technical details, architectural decisions, and important implementation notes for future development sessions.

## Project Overview

LLM Council is a 3-stage deliberation system where multiple LLMs collaboratively answer user questions. The key innovation is anonymized peer review in Stage 2, preventing models from playing favorites.

**How it works:**
1. **Stage 1**: All council LLMs respond to the user query independently
2. **Stage 2**: Each LLM evaluates and ranks the anonymized responses from Stage 1
3. **Stage 3**: A designated Chairman LLM synthesizes all responses and rankings into a final answer

## Quick Start

```bash
# Install dependencies
uv sync
cd frontend && npm install && cd ..

# Run (auto-starts CLIProxyAPIPlus proxy)
uv run python -m backend.main
# In another terminal:
cd frontend && npm run dev
```

First run triggers an interactive setup wizard for OAuth authentication.

## Architecture

### Project Structure

```
llm-council/
├── backend/
│   ├── main.py          # FastAPI app, proxy management, setup wizard
│   ├── council.py       # 3-stage orchestration logic
│   ├── openrouter.py    # LLM API client (via CLIProxyAPIPlus)
│   ├── config.py        # Model configuration
│   ├── storage.py       # JSON conversation persistence
│   └── start_proxy.py   # Standalone proxy setup script
├── frontend/
│   └── src/
│       ├── App.jsx              # Main orchestration
│       ├── api.js               # Backend API client
│       └── components/
│           ├── Sidebar.jsx      # Conversation list
│           ├── ChatInterface.jsx # Message input
│           ├── Stage1.jsx       # Individual responses tabs
│           ├── Stage2.jsx       # Peer rankings + aggregate
│           └── Stage3.jsx       # Final synthesis
├── cliproxy/            # CLIProxyAPIPlus binary & config (auto-created)
├── data/conversations/  # JSON conversation storage
└── start.sh             # Simple start script
```

### Backend (`backend/`)

**`config.py`**
- `COUNCIL_MODELS`: List of model identifiers (e.g., `openai/gpt-5.2`, `anthropic/claude-sonnet-4.5`)
- `CHAIRMAN_MODEL`: Model that synthesizes the final answer
- `CLIPROXY_API_URL`: Proxy endpoint (default: `http://localhost:8080/v1/chat/completions`)
- **Minimum 2 providers required** for council deliberation

Current default council:
```python
COUNCIL_MODELS = [
    "openai/gpt-5.2",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4.5",
    "anthropic/claude-haiku-4",
]
CHAIRMAN_MODEL = "openai/gpt-5.2"
```

**`openrouter.py`** (misnamed, actually uses CLIProxyAPIPlus)
- `query_model()`: Single async model query with configurable timeout
- `query_models_parallel()`: Parallel queries using `asyncio.gather()`
- Returns dict with `content` and optional `reasoning_details`
- Graceful degradation: returns `None` on failure, continues with successful responses

**`council.py`** - Core Logic
- `stage1_collect_responses()`: Parallel queries to all council models
- `stage2_collect_rankings()`: Anonymizes responses, collects peer evaluations
- `stage3_synthesize_final()`: Chairman produces final synthesis
- `parse_ranking_from_text()`: Extracts "FINAL RANKING:" section from model output
- `calculate_aggregate_rankings()`: Computes average rank across all evaluations
- `generate_conversation_title()`: Uses Gemini 2.5 Flash to generate short titles

**`storage.py`**
- JSON-based persistence in `data/conversations/`
- Conversation format: `{id, created_at, title, messages[]}`
- Assistant messages: `{role, stage1, stage2, stage3}`
- Note: Metadata (label_to_model, aggregate_rankings) is NOT persisted, only returned via API

**`main.py`** - FastAPI Application
- Port: **8001** (hardcoded)
- Auto-starts CLIProxyAPIPlus on startup
- Interactive setup wizard for first-time configuration
- CORS enabled for `localhost:5173` and `localhost:3000`
- Two message endpoints: batch and streaming (SSE)

Key endpoints:
- `GET /api/conversations` - List all conversations
- `POST /api/conversations` - Create new conversation
- `GET /api/conversations/{id}` - Get conversation details
- `POST /api/conversations/{id}/message` - Send message (batch)
- `POST /api/conversations/{id}/message/stream` - Send message (SSE streaming)

**`start_proxy.py`** - Standalone Proxy Setup
- Downloads platform-appropriate CLIProxyAPIPlus binary
- Manages OAuth authentication for providers
- Can be run independently: `python backend/start_proxy.py all`

### Frontend (`frontend/src/`)

**`App.jsx`**
- Manages conversation state and streaming message updates
- Handles progressive UI updates as each stage completes
- Stores metadata in UI state (not persisted)

**`api.js`**
- `sendMessageStream()`: SSE client for progressive stage updates
- Parses Server-Sent Events from `/message/stream` endpoint

**Components:**
- `Stage1.jsx`: Tab view of individual model responses
- `Stage2.jsx`: Tab view of evaluations + de-anonymized model names + aggregate rankings
- `Stage3.jsx`: Final chairman synthesis (green-tinted background)
- `ChatInterface.jsx`: Message input (Enter to send, Shift+Enter for newline)

**Styling:**
- Light mode theme, primary color `#4a90e2`
- `.markdown-content` class for consistent markdown spacing (12px padding)
- React 19 + Vite 7 + react-markdown

## CLIProxyAPIPlus Integration

The project uses **CLIProxyAPIPlus** instead of direct API calls. This proxy:
- Uses OAuth for authentication (no API keys needed in `.env`)
- Stores tokens in `cliproxy/auths/` directory
- Provides OpenAI-compatible API at `http://localhost:8080/v1/chat/completions`
- Supports multiple providers: OpenAI, Google (Gemini), Anthropic (Claude)

### First-Time Setup

When you first run `uv run python -m backend.main`, an interactive wizard runs:
1. Downloads the CLIProxyAPIPlus binary for your platform
2. Creates default configuration
3. Prompts for OAuth login to each provider (browser-based)
4. Requires minimum 2 providers for council functionality

### Manual Provider Setup

```bash
# Add a provider later
python backend/start_proxy.py login --provider openai
python backend/start_proxy.py login --provider gemini
python backend/start_proxy.py login --provider claude
```

### Checking Provider Status

Auth tokens are stored in `cliproxy/auths/{provider}.json`. The backend checks these files to determine which providers are available.

## Key Design Decisions

### Stage 2 Prompt Format
Strict format requirements ensure parseable output:
```
1. Evaluate each response individually first
2. Provide "FINAL RANKING:" header (all caps, with colon)
3. Numbered list format: "1. Response C", "2. Response A", etc.
4. No additional text after ranking section
```

### De-anonymization Strategy
- Models receive: "Response A", "Response B", etc.
- Backend creates mapping: `{"Response A": "openai/gpt-5.2", ...}`
- Frontend displays model names in **bold** for readability
- Users see explanation that original evaluation used anonymous labels

### Streaming Architecture
- SSE (Server-Sent Events) for progressive UI updates
- Events: `stage1_start`, `stage1_complete`, `stage2_start`, etc.
- Title generation runs in parallel with stage processing
- Optimistic UI updates with rollback on error

### Graceful Degradation
- Continue with successful responses if some models fail
- Never fail entire request due to single model failure
- Minimum 2 responses needed for meaningful council deliberation

## Development Commands

```bash
# Backend
uv run python -m backend.main          # Start backend (port 8001)
uv run python -m backend.start_proxy   # Proxy management CLI

# Frontend
cd frontend
npm run dev      # Development server (port 5173)
npm run build    # Production build
npm run lint     # ESLint

# Combined start
./start.sh       # Starts both backend and frontend
```

## Common Gotchas

1. **Module Imports**: Always run backend as `python -m backend.main` from project root
2. **Port Conflicts**: Backend uses 8001 (not 8000), proxy uses 8080
3. **CORS**: Frontend must match allowed origins in `main.py`
4. **Ranking Parse Failures**: Fallback regex extracts "Response X" patterns in order
5. **Missing Metadata**: Metadata is ephemeral, only in API responses
6. **Proxy Not Running**: Backend auto-starts it, but check `cliproxy/` exists
7. **Auth Expired**: Re-run OAuth login if requests fail

## Data Flow

```
User Query
    ↓
Stage 1: Parallel queries → [individual responses]
    ↓                            (SSE: stage1_complete)
Stage 2: Anonymize → Parallel ranking queries → [evaluations + parsed rankings]
    ↓                                                  (SSE: stage2_complete)
Aggregate Rankings Calculation → [sorted by avg position]
    ↓
Stage 3: Chairman synthesis with full context
    ↓                            (SSE: stage3_complete)
Return: {stage1, stage2, stage3, metadata}
    ↓
Frontend: Progressive display with tabs + validation UI
```

## Configuration Reference

### Environment Variables (`.env`)
```bash
# Optional - CLIProxyAPIPlus uses OAuth, not API keys
CLIPROXY_API_KEY=           # Usually empty
CLIPROXY_API_URL=http://localhost:8080/v1/chat/completions
```

### Ports
| Service | Port |
|---------|------|
| Backend (FastAPI) | 8001 |
| Frontend (Vite) | 5173 |
| CLIProxyAPIPlus | 8080 |

### File Locations
- Conversations: `data/conversations/{uuid}.json`
- Proxy binary: `cliproxy/cliproxy` (or `.exe` on Windows)
- Proxy config: `cliproxy/config.yaml`
- OAuth tokens: `cliproxy/auths/{provider}.json`

## Testing

```bash
# Test proxy connectivity
curl http://localhost:8080/health

# Test backend
curl http://localhost:8001/

# Quick model test (requires auth)
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "openai/gpt-5.2", "messages": [{"role": "user", "content": "Hello"}]}'
```

## Future Enhancement Ideas

- Configurable council/chairman via UI
- Model performance analytics over time
- Export conversations to markdown/PDF
- Custom ranking criteria beyond accuracy/insight
- Support for reasoning models with extended thinking
- Multi-turn conversation context in deliberation
