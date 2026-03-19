# Agentic Talent Intelligence Platform

> An AI Hackathon MVP — Skills-verified, bias-free candidate matching powered by a Multi-Agent System.

## 🏗️ Project Structure

```
eightfold/
├── backend/                  # FastAPI + AI backend (Python)
│   ├── __init__.py
│   ├── config.py             # Central env-based settings
│   ├── logger.py             # Shared logging setup
│   ├── github_scraper.py     # GitHub public profile + dependency parser
│   ├── codeforces_scraper.py # Codeforces rating / contest history
│   ├── pdf_parser.py         # PDF resume → raw text          [Phase 2]
│   ├── anonymizer_agent.py   # LLM-based PII stripping        [Phase 2]
│   ├── vector_db.py          # ChromaDB embed + match engine  [Phase 3]
│   ├── evaluation_agents.py  # Tech Lead / Trajectory / Explainability [Phase 4]
│   └── main.py               # FastAPI entry point            [Phase 5]
│
├── frontend/                 # Next.js dashboard              [Phase 5]
│
├── requirements.txt
├── .env.example
└── README.md
```

## 🚀 Quick Start

### 1. Clone & install Python deps
```bash
git clone <repo-url>
cd eightfold
python -m venv venv
# Windows
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Set up environment
```bash
copy .env.example .env
# Edit .env with your API keys
```

### 3. Run the backend (after Phase 5)
```bash
uvicorn backend.main:app --reload --port 8000
```

### 4. Run the frontend (after Phase 5)
```bash
cd frontend
npm install
npm run dev
```

## 🔑 Environment Variables

| Variable | Description | Default |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key | — |
| `GOOGLE_API_KEY` | Google Gemini API key | — |
| `LLM_PROVIDER` | `openai` or `gemini` | `openai` |
| `LLM_MODEL` | Model name | `gpt-4o` |
| `GITHUB_TOKEN` | GitHub Personal Access Token | — |
| `USE_MOCK_DATA` | `True` to skip live API calls | `False` |
| `CHROMA_PERSIST_DIR` | ChromaDB storage directory | `./chroma_db` |

## 🧪 Demo / Hackathon Fallback

Set `USE_MOCK_DATA=True` in your `.env` to use pre-canned data for **all** external API calls (GitHub + Codeforces). This ensures a flawless live demo even if rate limits are hit.

## 📦 Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Python 3.10+ |
| Frontend | Next.js + React |
| LLM / Agents | LangChain + OpenAI GPT-4o / Gemini |
| Vector DB | ChromaDB (local) |
| External APIs | GitHub REST API, Codeforces API |

## 🤖 Agents

1. **Tech Lead Agent** — Compares resume-claimed skills vs. GitHub-verified dependencies
2. **Trajectory Agent** — Scores learning velocity (1–5) from commit history and rating trends
3. **Explainability Agent** — Writes a 3-sentence recruiter-facing justification
