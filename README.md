# 🧠 Eightfold AI — Agentic Talent Intelligence Platform

> An AI Hackathon MVP that moves beyond traditional resume screening.  
> Skills are **verified**, candidates are **anonymized** to prevent bias, and every hiring decision is **explained** by AI agents.

---

## 📖 Table of Contents

1. [What Problem Does This Solve?](#what-problem-does-this-solve)
2. [How It Works — End-to-End Flow](#how-it-works--end-to-end-flow)
3. [Architecture Diagram](#architecture-diagram)
4. [Module-by-Module Breakdown](#module-by-module-breakdown)
5. [The Three AI Agents](#the-three-ai-agents)
6. [Composite Scoring Formula](#composite-scoring-formula)
7. [API Reference](#api-reference)
8. [Project Structure](#project-structure)
9. [Tech Stack](#tech-stack)
10. [Quick Start](#quick-start)
11. [Environment Variables](#environment-variables)
12. [Demo / Hackathon Fallback](#demo--hackathon-fallback)

---

## What Problem Does This Solve?

Traditional recruitment tools suffer from three critical flaws:

| Problem | Traditional ATS | This Platform |
|---|---|---|
| **Resume lying** | Takes skills at face value | Verifies skills against real GitHub code |
| **Hiring bias** | Exposes name, gender, location | Auto-strips all PII before analysis |
| **Black-box decisions** | Shows only a score | 3 AI agents write a recruiter justification |

This platform builds a **Multi-Agent System (MAS)** where specialized AI agents inspect candidates from multiple angles and produce a ranked, scored, and explained pipeline — in seconds.

---

## How It Works — End-to-End Flow

```
RECRUITER                   SYSTEM                              AI AGENTS
─────────                   ──────                              ─────────
Upload PDF ──────────────► pdf_parser.py
                               │ (raw text)
                               ▼
                         anonymizer_agent.py ◄── LangChain + LLM
                               │ (PII-free JSON profile)
                               │
Enter GitHub URL ────────► github_scraper.py
                               │ (real repo deps, languages)
                               │
Enter CF Handle ─────────► codeforces_scraper.py
                               │ (rating, rank, contest history)
                               │
                         ┌─────▼──────┐
                         │ vector_db  │ ◄── ChromaDB (cosine similarity)
                         └─────┬──────┘
                               │
Paste Job Description ───────► get_top_matches()
                               │ (top-k candidates ranked by similarity)
                               │
                         evaluation_agents.py
                           ├── TechLeadAgent    → skill verification
                           ├── TrajectoryAgent  → learning velocity (1–5)
                           └── ExplainabilityAgent → 3-sentence justification
                               │
                         Synthesizer (weighted final_score)
                               │
                         Next.js Dashboard ◄── recruiter sees ranked cards
```

---

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                          FRONTEND (Next.js)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐│
│  │ UploadPanel  │  │   JDPanel    │  │   CandidateCard ×N    ││
│  │ drag & drop  │  │ textarea JD  │  │ score ring + agents   ││
│  └──────┬───────┘  └──────┬───────┘  └───────────────────────┘│
└─────────┼─────────────────┼──────────────────────────────────-─┘
          │ POST /api/       │ POST /api/match
          │ upload-candidate │
┌─────────┼─────────────────┼────────────────────────────────────┐
│         │   FASTAPI BACKEND (main.py)        │                  │
│  ┌──────▼───────┐   ┌─────▼──────┐          │                  │
│  │ pdf_parser   │   │  vector_db │◄──────────┘                  │
│  │ anonymizer   │   │  ChromaDB  │                              │
│  │ gh_scraper   │   └─────┬──────┘                              │
│  │ cf_scraper   │         │                                     │
│  └──────┬───────┘         │ top-k matches                       │
│         └────────────────►│                                     │
│                    ┌──────▼─────────────────────┐              │
│                    │     evaluation_agents.py    │              │
│                    │  TechLead + Trajectory +    │              │
│                    │  Explainability + Synthesizer│              │
│                    └─────────────────────────────┘              │
└────────────────────────────────────────────────────────────────┘
          │
    LLM API (OpenAI GPT-4o / Google Gemini)
    External APIs (GitHub REST, Codeforces API)
    ChromaDB (local disk persistence)
```

---

## Module-by-Module Breakdown

### `backend/pdf_parser.py`
Extracts raw text from uploaded PDF resumes using a two-library strategy:
1. **PyPDF2** — fast, handles standard text-based PDFs
2. **pdfminer.six** (fallback) — slower but handles complex layouts, multi-column, non-standard encoding

Exposes two functions:
- `extract_text_from_pdf(file_path)` — file on disk
- `extract_text_from_pdf_bytes(pdf_bytes)` — in-memory bytes (for FastAPI `UploadFile`)

---

### `backend/anonymizer_agent.py`
A **LangChain LCEL chain** that takes raw resume text and:
1. **Strips all PII**: names, emails, phone numbers, addresses, LinkedIn URLs, gender markers, age/DOB
2. **Structures the output** into a strict JSON schema with skills, work history, projects, education, and certifications
3. Includes robust JSON parsing that handles markdown fences and extra prose from LLMs

**Why anonymize?** Removing identity signals forces the system (and ultimately the recruiter) to evaluate purely on capability — reducing unconscious bias.

Output schema:
```json
{
  "skills": ["Python", "FastAPI"],
  "years_of_experience": 5,
  "education": [{"degree": "...", "institution": "[Redacted]", "year": 2020}],
  "work_history": [{"role": "...", "company": "[Redacted]", "duration_months": 24, "key_achievements": [...]}],
  "certifications": [...],
  "projects": [{"name": "...", "description": "...", "tech_stack": [...]}],
  "pii_removed": true
}
```

---

### `backend/github_scraper.py`
Fetches real evidence of a candidate's coding activity from **GitHub's REST API**:

1. **Profile stats** — public repos count, followers, following
2. **Top 5 repos** — sorted by stars, including language, description, and topics
3. **Language distribution** — percentage breakdown across all public repos
4. **Dependency verification** — fetches `requirements.txt` and `package.json` from each repo and parses the actual libraries used

This is the **anti-lying layer**: a candidate claiming "I know FastAPI" is checked against whether any of their repos actually depend on `fastapi` in their package manifests.

Requires a GitHub Personal Access Token in `.env` (increases rate limit from 60 to 5,000 requests/hour).

---

### `backend/codeforces_scraper.py`
Fetches competitive programming data from the **Codeforces public API**:

- `user.info` → current/max rating, rank title, contribution score
- `user.rating` → full contest history (count, recent deltas)
- `user.status` → approximation of solved problem count (distinct accepted submissions)

**Safe-by-design**: if a handle doesn't exist or the API is unreachable, it returns a clean dict with `null` values and an `error` message — it never crashes the pipeline.

Codeforces rank titles: `Newbie → Pupil → Specialist → Expert → Candidate Master → Master → International Master → Grandmaster → International Grandmaster → Legendary Grandmaster`

---

### `backend/vector_db.py`
The **semantic matching engine** using ChromaDB:

1. **Embedding**: Converts candidate profiles and JDs to dense vector embeddings using OpenAI `text-embedding-3-small` or Google Gemini embeddings
2. **Profile serialization**: Converts the JSON candidate profile into a rich natural-language document before embedding (skills, role history, projects, verified deps, CF rating all included)
3. **Storage**: ChromaDB persists data to disk (`./chroma_db/`) — survives restarts
4. **Retrieval**: Uses cosine similarity to find the top-k most semantically relevant candidates for a given JD
5. **Score conversion**: ChromaDB returns cosine *distance* [0, 2]. We convert: `similarity = 1 - (distance / 2)` → gives [0, 1]

---

### `backend/evaluation_agents.py`
Three LangChain-powered LLM agents that run **after** vector retrieval:

_(See [The Three AI Agents](#the-three-ai-agents) section below)_

---

### `backend/main.py`
FastAPI server that ties everything together. Exposes 7 REST endpoints, handles file uploads via `multipart/form-data`, and caches each processed candidate in memory to avoid re-running the full pipeline on every match query.

---

## The Three AI Agents

### Agent 1: 🔬 Tech Lead Agent
**Purpose**: Verify if the candidate is telling the truth about their skills.

**Input**: List of claimed skills (from anonymized resume) + list of verified dependencies (from GitHub)

**Process**: Compares the two lists — any claimed skill that appears in actual `requirements.txt`/`package.json` files is marked verified. The rest are flagged as unverified claims.

**Output**:
```json
{
  "verified_skills": ["Python", "FastAPI", "scikit-learn"],
  "unverified_claims": ["Kubernetes", "Spark"],
  "verification_rate": 0.71,
  "verdict": "Strong alignment — most core skills are GitHub-verified."
}
```

---

### Agent 2: 📈 Trajectory Agent
**Purpose**: Score how fast the candidate is growing as a developer.

**Input**: Work history, projects, Codeforces contest history and rating trend

**Process**: The LLM analyzes the *arc* of the candidate's career — are they taking on more complex systems? Increasing their competitive programming rating? Leading teams? The score is holistic.

**Scoring rubric**:
| Score | Meaning |
|---|---|
| 1 | Stagnant — repetitive roles, no visible skill growth |
| 2 | Slow — minor incremental improvement |
| 3 | Steady — consistent, reasonable growth |
| 4 | Fast — clear skill expansion, increasing impact |
| 5 | Exceptional — rapid multi-domain growth, leadership, innovation |

---

### Agent 3: 💬 Explainability Agent
**Purpose**: Write a recruiter-facing justification so hiring decisions are never a black box.

**Input**: JD text, vector similarity score, Tech Lead findings, Trajectory score

**Output**: Exactly **3 sentences** structured as:
1. Strongest technical evidence (specific verified skills/GitHub data)
2. Learning trajectory and growth potential
3. Overall hiring recommendation with confidence level

**Example output**:
> *This candidate demonstrates strong Python and FastAPI expertise confirmed through direct GitHub dependency analysis, with 71% of claimed skills verified in production codebases. Their Codeforces rating improvement of +320 over 24 months and consistent progression from junior backend to distributed systems engineering indicates fast, multi-domain learning. Overall a high-confidence match for the Senior Backend Engineer role, with Kubernetes and Spark claims warranting brief technical interview verification.*

---

## Composite Scoring Formula

The final score that drives candidate ranking is a **weighted composite** of three signals:

```
final_score = (vector_similarity  × 0.40)
            + (verification_rate  × 0.30)
            + (trajectory_score/5 × 0.30)
```

| Component | Weight | What It Measures |
|---|---|---|
| Vector Similarity | **40%** | Semantic relevance of the candidate's full profile to the JD |
| Verification Rate | **30%** | What % of resume claims are backed by real GitHub code |
| Trajectory Score | **30%** | Learning velocity and career growth (1–5 normalized) |

This weighting intentionally penalizes inflated resumes (low verification rate) even if the semantic similarity is high.

---

## API Reference

Base URL: `http://localhost:8000`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/upload-candidate` | Upload PDF + GitHub/CF → run full ingestion pipeline |
| `POST` | `/api/add-jd` | Store a JD in ChromaDB |
| `POST` | `/api/match` | Run vector match + all 3 agents → ranked results |
| `GET` | `/api/candidates` | List all stored candidate IDs |
| `DELETE` | `/api/candidates/{id}` | Remove a specific candidate |
| `DELETE` | `/api/reset` | ⚠️ Wipe all data (demo reset) |

### `POST /api/upload-candidate`
```
Content-Type: multipart/form-data

Fields:
  resume            (file, required)   — PDF resume file
  github_username   (string, optional) — GitHub username
  codeforces_handle (string, optional) — Codeforces handle
  candidate_label   (string, optional) — Custom ID (auto-generated if omitted)
```

### `POST /api/match`
```json
{
  "jd_text": "We are looking for a Senior Python engineer...",
  "top_k": 5
}
```

Response: Ranked array of `MatchResult` objects with scores, verified skills, trajectory, and explanation.

---

## Project Structure

```
eightfold/
├── backend/
│   ├── __init__.py
│   ├── config.py               ← Central env settings
│   ├── logger.py               ← Shared logger factory
│   ├── pdf_parser.py           ← Phase 1: PDF text extraction
│   ├── github_scraper.py       ← Phase 1: GitHub profile + deps
│   ├── codeforces_scraper.py   ← Phase 1: CF rating/contests
│   ├── anonymizer_agent.py     ← Phase 2: LLM PII stripping
│   ├── vector_db.py            ← Phase 3: ChromaDB embed + match
│   ├── evaluation_agents.py    ← Phase 4: 3 agents + synthesizer
│   └── main.py                 ← Phase 5: FastAPI server
│
├── frontend/
│   ├── next.config.js          ← API proxy config
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── app/
│       │   ├── layout.tsx      ← Root layout + fonts + toasts
│       │   ├── globals.css     ← Dark design system
│       │   └── page.tsx        ← Main dashboard
│       └── components/
│           ├── UploadPanel.tsx ← PDF drag-drop + inputs
│           ├── JDPanel.tsx     ← JD textarea + save
│           ├── CandidateCard.tsx ← Ranked result card
│           └── StatsBar.tsx    ← Live pipeline metrics
│
├── chroma_db/                  ← Auto-created, ChromaDB persistence
├── requirements.txt
├── .env.example
└── README.md
```

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Backend** | FastAPI + Python 3.10+ | Async, fast, automatic API docs |
| **Frontend** | Next.js 14 + React + TypeScript | SSR-ready, great DX, built-in proxy |
| **LLM / Agents** | LangChain LCEL + OpenAI GPT-4o / Gemini | Composable chains, dual-provider support |
| **Vector DB** | ChromaDB (local) | Zero-infra, persistent, open source |
| **Embeddings** | OpenAI `text-embedding-3-small` / Gemini | State-of-art semantic search |
| **PDF Parsing** | PyPDF2 + pdfminer.six | Redundant fallback for robustness |
| **GitHub Data** | GitHub REST API | Real dependency verification |
| **Coding Stats** | Codeforces Public API | Objective algorithmic skill signal |
| **Animations** | Framer Motion | Smooth UI transitions |
| **Icons** | Lucide React | Consistent, lightweight iconset |

---

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- An OpenAI API key OR Google Gemini API key
- (Optional) GitHub Personal Access Token for higher API rate limits

### 1. Clone and set up the backend

```powershell
cd "C:\Users\Kuldeep Sharma\Desktop\eightfold"

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate

# Install all Python dependencies
pip install -r requirements.txt

# Copy the example env file and fill in your keys
copy .env.example .env
```

Edit `.env`:
```env
OPENAI_API_KEY=sk-your-key-here
GITHUB_TOKEN=ghp_your-token-here
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
USE_MOCK_DATA=False
```

### 2. Start the backend

```powershell
uvicorn backend.main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` to see the auto-generated Swagger UI.

### 3. Start the frontend (new terminal)

```powershell
cd "C:\Users\Kuldeep Sharma\Desktop\eightfold\frontend"
npm install
npm run dev
```

Visit `http://localhost:3000` to use the dashboard.

### 4. Using the dashboard

1. **Upload Candidates tab**: Drop a PDF resume. Optionally add a GitHub username and Codeforces handle. Click **Ingest Candidate**. Repeat for all candidates.
2. **Job Description tab**: Paste your JD (or click "Use Sample"). Optionally save it to the vector DB.
3. Click **Match Candidates** — the AI agents run and results appear ranked by final score.
4. Click any card to expand it and see verified skills, unverified claims, score breakdown, and the AI explanation.

---

## Environment Variables

| Variable | Required | Description | Default |
|---|---|---|---|
| `OPENAI_API_KEY` | If using OpenAI | OpenAI API key | — |
| `GOOGLE_API_KEY` | If using Gemini | Google Gemini API key | — |
| `LLM_PROVIDER` | No | `openai` or `gemini` | `openai` |
| `LLM_MODEL` | No | Model name (e.g. `gpt-4o`) | `gpt-4o` |
| `GITHUB_TOKEN` | Recommended | GitHub PAT for higher rate limits | — |
| `USE_MOCK_DATA` | No | `True` to skip all external APIs | `False` |
| `CHROMA_PERSIST_DIR` | No | ChromaDB storage directory | `./chroma_db` |
| `APP_PORT` | No | FastAPI server port | `8000` |

---

## Demo / Hackathon Fallback

> 🛡️ **Never crash during a live demo.**

Set `USE_MOCK_DATA=True` in your `.env` file. This activates pre-canned data for **every** external call:

| Module | Mock behavior |
|---|---|
| `github_scraper.py` | Returns a realistic profile for "octocat" with 8 repos, Python/JS distribution, and verified deps |
| `codeforces_scraper.py` | Returns "tourist" profile — Legendary Grandmaster, 247 contests, 3979 max rating |
| `anonymizer_agent.py` | Returns a Senior Software Engineer profile with 5 years experience and ML skills |
| `evaluation_agents.py` | Returns pre-written agent outputs with 71% verification rate, trajectory score 4/5 |

With `USE_MOCK_DATA=True`, **no API keys are required** — the entire pipeline runs locally, instantly.

---

## Testing Individual Modules

Each backend module can be run directly from the command line for quick testing:

```powershell
# Test GitHub scraper
python -m backend.github_scraper torvalds

# Test Codeforces scraper
python -m backend.codeforces_scraper tourist

# Test PDF parser
python -m backend.pdf_parser path\to\resume.pdf

# Test anonymizer (uses pdf_parser internally)
python -m backend.anonymizer_agent path\to\resume.pdf

# Test vector DB with sample data
python -m backend.vector_db

# Test evaluation agents (uses mock data)
python -m backend.evaluation_agents
```

---

*Built for the AI Hackathon 2026 — Agentic Talent Intelligence.*
