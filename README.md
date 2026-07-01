# Shadow PO

An AI-powered cognitive mentor that helps software engineers understand ambiguous product requirements during Sprint Refinements and Product Discovery sessions.

Shadow PO translates high-level business intent into explicit engineering implications, generates critical questions for cross-examining the Product Owner, and packages the team's understanding into structured specification artifacts — all while keeping sensitive information on your machine.

---

## What it does

- **Chat** with your feature docs, meeting transcripts, and the web to clarify requirements
- **Transcribe** audio/video meetings locally — no audio ever leaves your machine
- **Generate docs** on demand: business rules, Gherkin scenarios, Mermaid diagrams, and open questions
- **Track answered questions** so future doc generation reflects what the PO has already clarified
- **Privacy-first** — everything passes through a local scrubber before any network call

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.14+ | Managed by `uv` |
| [uv](https://docs.astral.sh/uv/) | latest | Package manager |
| [Docker](https://www.docker.com/) | any | For SearXNG (web grounding) |
| [ffmpeg](https://ffmpeg.org/) | any | For video transcription |
| NVIDIA NIM API key | — | Free tier at [build.nvidia.com](https://build.nvidia.com) |

### Install uv (if not already installed)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Install ffmpeg

```bash
# Windows (Chocolatey)
choco install ffmpeg

# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg
```

---

## Setup

Quick checklist:

1. `uv sync`
2. Add `NVIDIA_API_KEY` to `.env`
3. *(Optional)* `docker compose -f docker-compose.searxng.yml up -d` for web grounding
4. `uv run streamlit run app.py`

### 1. Clone the repository

```bash
git clone <repo-url>
cd shadow-product-owner
```

### 2. Install dependencies

```bash
uv sync
```

This creates a virtual environment and installs all dependencies automatically.

### 3. Set your NVIDIA API key

Create a `.env` file in the project root:

```bash
# .env
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Get a free API key at [build.nvidia.com](https://build.nvidia.com) — no credit card required.

### 4. (Optional) Review `settings.yaml`

The default configuration works out of the box. Edit if you need to change any of these:

```yaml
# settings.yaml

workspaces_root: "workspaces/"   # where feature workspaces are stored

model:
  name: "nvidia/nemotron-3-ultra-550b-a55b"   # NVIDIA NIM free-tier model
  temperature: 0.2

searxng_url: "http://localhost:8080"          # local SearXNG instance

whisper:
  model_size: "base"    # tiny | base | small | medium | large-v3
  device: "cpu"         # cpu | cuda
  compute_type: "int8"  # int8 | float16 | float32

embedding_model: "sentence-transformers/all-MiniLM-L6-v2"

privacy:
  codenames: []   # e.g. ["Project Titan", "Project Alpha"]
```

**Whisper model sizes** — tradeoff between speed and accuracy:

| Size | Speed | Accuracy | Recommended for |
|---|---|---|---|
| `tiny` | fastest | lowest | development / testing |
| `base` | fast | good | default |
| `small` | moderate | better | noisy recordings |
| `medium` | slow | high | important meetings |
| `large-v3` | slowest | highest | critical accuracy needed |

**Custom codenames** — add any internal project names you don't want sent to the LLM:

```yaml
privacy:
  codenames: ["Project Titan", "Codename Phoenix", "Operation Atlas"]
```

### 5. Start SearXNG (web grounding)

Web grounding is optional — the app works without it but will tell you when a search was attempted but unavailable.

Shadow PO calls SearXNG's JSON search API. The default Docker image only enables HTML output, so requests with `format=json` return **HTTP 403** unless you mount the bundled settings file (which enables JSON and disables the bot limiter for local use).

**Recommended — Docker Compose:**

```bash
docker compose -f docker-compose.searxng.yml up -d
```

**Alternative — plain Docker:**

```bash
# macOS / Linux
docker run -d -p 8080:8080 \
  -v ./docker/searxng/settings.yml:/etc/searxng/settings.yml:ro \
  searxng/searxng

# Windows (PowerShell)
docker run -d -p 8080:8080 `
  -v ${PWD}/docker/searxng/settings.yml:/etc/searxng/settings.yml:ro `
  searxng/searxng
```

**Verify SearXNG is working:**

```bash
curl -X POST http://localhost:8080/search -d "q=test&format=json"
```

You should get a JSON response (not `403 Forbidden`). The UI is also available at [http://localhost:8080](http://localhost:8080).

**Stop SearXNG:**

```bash
docker compose -f docker-compose.searxng.yml down
```

The URL must match `searxng_url` in `settings.yaml` (default: `http://localhost:8080`).

---

## Running the app

```bash
uv run streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

> **Note:** The first run downloads the Whisper speech model and the sentence-transformers embedding model. This takes a few minutes on first launch — subsequent runs are instant.

---

## First walkthrough

1. **Create a workspace** — in the sidebar, type a feature name (e.g. `one-click-checkout`) and click "Create workspace"
2. **Upload a document** — go to the Upload tab, select a PDF or Word doc and click "Save & Index"
3. **Chat** — switch to the Chat tab and ask a question about the feature
4. **Upload a recording** *(optional)* — upload an audio or video file; it transcribes locally then lets you save it
5. **Record an answered question** — if the PO clarifies something during chat, tell the app and it records the Q&A pair
6. **Generate docs** — click the Generate Docs tab and hit the button to produce `business-rules.md`, `scenarios.md`, `diagram.md`, and `open-questions.md`

---

## Project structure

```
shadow-product-owner/
├── app.py                        # Streamlit entry point
├── settings.yaml                 # App configuration
├── docker-compose.searxng.yml    # SearXNG service (web grounding)
├── .env                          # API keys (not committed)
├── requirements.txt              # Legacy pip requirements
├── pyproject.toml                # uv project definition
│
├── docker/
│   └── searxng/
│       └── settings.yml          # Enables JSON API for web grounding
│
├── shadow_po/                    # Application source
│   ├── config.py                 # settings.yaml loader
│   ├── workspace.py              # Workspace folder management
│   ├── privacy.py                # Presidio PII scrubber
│   ├── transcription.py          # faster-whisper wrapper
│   ├── knowledge_base.py         # MarkItDown + chunking + Chroma RAG
│   ├── web_grounding.py          # SearXNG client
│   ├── pipeline.py               # LLM orchestration (ChatNVIDIA)
│   ├── chat_history.py           # Conversation persistence
│   ├── answered_questions.py     # Q&A detection and tracking
│   ├── generate_docs.py          # "Generate docs" orchestration
│   ├── schemas.py                # Pydantic output schemas
│   ├── ui_workspace.py           # Sidebar workspace picker
│   ├── ui_chat.py                # Chat panel
│   ├── ui_upload.py              # File upload panel
│   └── ui_generate.py            # Generate docs panel
│
├── prompts/
│   └── generate_docs_system_prompt.md   # LLM system prompt for doc generation
│
├── workspaces/                   # Runtime per-feature workspaces (not committed)
│   └── <feature-name>/
│       ├── input/
│       │   ├── documents/        # Source specs, PDFs, etc.
│       │   └── meetings/         # Saved meeting transcripts
│       ├── progress/
│       │   └── chat/             # Saved conversation files
│       └── output/
│           └── <timestamp>/      # Generated docs snapshots
│               ├── business-rules.md
│               ├── scenarios.md
│               ├── diagram.md
│               └── open-questions.md
│
├── tests/                        # Pytest suite
├── SDD/                          # Spec-Driven Development artifacts
└── requeriments/                 # Business requirements and reports
```

---

## Running tests

```bash
# Run the full test suite
uv run pytest -v

# Run a specific component
uv run pytest tests/test_privacy.py -v
uv run pytest tests/test_knowledge_base.py -v
uv run pytest tests/test_pipeline.py -v

# Run with coverage
uv run pytest -v --cov=shadow_po
```

---

## Architecture overview

```
User Input
    │
    ▼
Privacy Scrubber (Presidio + custom codenames)
    │
    ├──► RAG Retrieval (MarkItDown → chunks → sentence-transformers → Chroma)
    │         per-feature index — zero cross-workspace leakage
    │
    ├──► Web Grounding (SearXNG) — only when question needs public info
    │         unavailability is disclosed explicitly, never silently swallowed
    │
    ▼
LLM (NVIDIA NIM — nemotron-3-ultra-550b-a55b)
    │    free tier · 1M token context · tool calling · structured output
    │
    ▼
Schema-validated answer (ShadowPOAnswer)
    │
    ├──► Chat History (progress/chat/<id>.md — append-only)
    │
    └──► Answered Questions detection → answered-questions.md → re-index
              │
              ▼
         "Generate Docs" → output/<timestamp>/
              business-rules.md  ·  scenarios.md  ·  diagram.md  ·  open-questions.md
```

### Privacy boundary

**Nothing crosses the network without being scrubbed first.** This applies to:
- Chat questions
- Document content sent to the LLM
- Search queries sent to SearXNG
- Meeting transcripts (audio never leaves the machine)

If the scrubber fails for any reason, the pipeline stops — it never falls back to sending raw text.

---

## Key dependencies

| Package | License | Purpose |
|---|---|---|
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | MIT | Local speech-to-text |
| [Presidio](https://github.com/microsoft/presidio) | MIT | Local PII detection & anonymization |
| [MarkItDown](https://github.com/microsoft/markitdown) | MIT | Local document conversion (PDF, DOCX, PPTX) |
| [sentence-transformers](https://www.sbert.net/) | Apache 2.0 | Local embeddings |
| [Chroma](https://www.trychroma.com/) | Apache 2.0 | Local vector store |
| [LangChain](https://www.langchain.com/) | MIT | LLM orchestration |
| [ChatNVIDIA](https://python.langchain.com/docs/integrations/chat/nvidia_ai_endpoints/) | MIT | NVIDIA NIM integration |
| [SearXNG](https://searxng.org/) | AGPL-3.0 | Self-hosted web search |
| [Streamlit](https://streamlit.io/) | Apache 2.0 | Web UI |

---

## Troubleshooting

**`NVIDIA_API_KEY not set`**
Add `NVIDIA_API_KEY=nvapi-...` to your `.env` file in the project root and restart the app.

**`ffmpeg is not available`**
Install ffmpeg — see [Prerequisites](#prerequisites). Required only for video transcription; audio files work without it.

**`Could not connect to SearXNG`**
SearXNG is not running or the URL in `settings.yaml` is wrong. Start it with `docker compose -f docker-compose.searxng.yml up -d`. The app continues without web grounding but will flag it in answers.

**`SearXNG returned HTTP 403`** / **`Web grounding was attempted but SearXNG was unavailable`**
The JSON search format is disabled on your SearXNG instance — common when starting the bare image without the bundled config. Fix:

```bash
# Stop any old container on port 8080, then:
docker compose -f docker-compose.searxng.yml up -d
```

Confirm with: `curl -X POST http://localhost:8080/search -d "q=test&format=json"`

**First run is slow**
The Whisper model (`base`, ~145 MB) and the embedding model (`all-MiniLM-L6-v2`, ~90 MB) download on first use. Subsequent starts use the local cache.

**Transcription quality is poor**
Try a larger Whisper model — change `whisper.model_size` in `settings.yaml` to `small` or `medium`. For GPU acceleration set `device: cuda` and `compute_type: float16`.

**Documents not found in chat answers**
Make sure you clicked "Save & Index" after uploading. Indexing is explicit, not automatic. You can re-index by uploading the document again.
