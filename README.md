<div align="center">

# CanCards AI

### AI-powered credit card recommendation system for Canadian users

CanCards AI is a smart credit card recommendation system designed for Canadian users. Just ask in natural language which card suits your needs, and our system will search, compare, and analyze top options in real time. Instead of random answers, you’ll get grounded, reliable recommendations with direct source links and explanations, so you can confidently pick the best card for you.

<br>

<a href="https://cancards-ai.vercel.app">
  <img src="https://img.shields.io/badge/LIVE-DEMO-43B3AE?style=for-the-badge&logo=vercel&logoColor=white" />
</a>

</div>

---

<br>

<p align="center">
  <img 
    src="https://res.cloudinary.com/dolt8nnzc/image/upload/v1778604923/HCI%20Assignment/CanCards-ai/CanCards_vektus.png" 
    alt="CanCards AI Homepage"
    width="68%"
  />
</p>

<p align="center">
  <strong>
    <sub>Homepage</sub>
  </strong>
</p>

<br><br>

<p align="center">
  <img 
    src="https://res.cloudinary.com/dolt8nnzc/image/upload/v1778648164/HCI%20Assignment/CanCards-ai/BrowsCards_y4dkhb.png" 
    alt="Browse Cards Page"
    width="68%"
  />
</p>

<p align="center">
  <strong>
    <sub>Browse & Compare Cards</sub>
  </strong>
</p>

<br>

---

**CanCards-AI** is a **full-stack RAG application** where users ask plain-English questions about Canadian credit cards and receive streamed, cited answers backed by a semantically indexed database of 50+ cards. Each query is embedded, matched against a **Pinecone vector store**, and passed with the retrieved context to **Claude Sonnet 4.6**, which streams a structured response token-by-token to the browser via SSE. Alongside the serving pipeline, a RAGAS evaluation harness runs weekly in CI- **GPT-4o-mini** acts as an independent judge and scores every response against 30 hand-curated ground-truth pairs across faithfulness, context precision, and answer relevancy. A regression above 5% from baseline fails the build. The full system is containerised with Docker, deployed to AWS Lightsail, and ships automatically through GitHub Actions on every merge to main.

---

## System Architecture
<img width="1536" height="1024" alt="ChatGPT Image May 12, 2026, 11_30_02 PM" src="https://github.com/user-attachments/assets/437a2fd0-2150-470b-be67-06cacec422a9" />


---

## Evaluation Flow

RAGAS runs in CI on a weekly schedule and on every manual trigger. GPT-4o-mini acts as an independent judge LLM, it has no knowledge of how the answer was generated, only the question, the retrieved context, and the answer. A score drop above 5% from baseline fails the build.


<img width="1536" height="1024" alt="ChatGPT Image May 12, 2026, 11_34_00 PM" src="https://github.com/user-attachments/assets/4b0c8562-3e02-4fb4-af78-60e0d6d79c3f" />



---

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 (App Router) · TypeScript · Tailwind CSS · shadcn/ui |
| Backend | Python 3.12 · FastAPI · Pydantic v2 |
| Embeddings | OpenAI `text-embedding-3-small` (1536-dim) |
| Generation | Anthropic Claude Sonnet 4.6 |
| Vector store | Pinecone Serverless |
| Orchestration | LangChain · LangSmith |
| Evaluation | RAGAS · GPT-4o-mini judge |
| Container | Docker multi-stage (linux/amd64) |
| Hosting | AWS Lightsail ca-central-1 · Vercel |
| CI / CD | GitHub Actions |

---

## Project structure

```
cancards-ai/
│
├── backend/
│   ├── app/
│   │   ├── clients/
│   │   │   ├── anthropic_client.py     Claude — batch + streaming
│   │   │   ├── openai_client.py        Embeddings
│   │   │   └── pinecone_client.py      Vector store
│   │   ├── rag/
│   │   │   ├── ingest.py               Card chunking + embedding pipeline
│   │   │   ├── retrieve.py             Semantic search
│   │   │   ├── generate.py             Structured response generation
│   │   │   └── stream.py               SSE streaming generator
│   │   ├── routers/
│   │   │   ├── ask.py                  POST /api/ask  ·  /api/ask/stream
│   │   │   ├── cards.py                GET  /api/cards
│   │   │   └── health.py               GET  /health
│   │   ├── config.py                   Env-driven Pydantic settings
│   │   ├── models.py                   Request / response schemas
│   │   └── main.py                     FastAPI entrypoint
│   │
│   ├── data/
│   │   └── cards.json                  Curated card database
│   ├── scripts/
│   │   └── ingest.py                   One-time Pinecone population
│   ├── tests/
│   │   ├── unit/                       20 tests — no external calls
│   │   │   ├── test_ingest.py
│   │   │   ├── test_generate.py
│   │   │   └── test_api.py
│   │   └── evals/
│   │       ├── ground_truth.json       30 hand-curated Q&A pairs
│   │       ├── run_evals.py            Eval runner + regression gate
│   │       └── baseline.json          Reference scores
│   │
│   ├── Dockerfile                      Multi-stage build
│   ├── pyproject.toml
│   └── requirements.txt
│
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── page.tsx                Chat interface
│       │   ├── cards/[id]/             Card detail
│       │   └── compare/               Side-by-side comparison
│       ├── components/
│       │   ├── chat/                   ChatInterface · MessageBubble · ChatInput
│       │   ├── cards/                  CreditCardCard · CardGrid
│       │   └── layout/                Navbar
│       ├── hooks/
│       │   └── useStreamingChat.ts    SSE-driven chat state
│       ├── lib/api.ts                 Typed backend client
│       └── types/index.ts            Shared TypeScript schemas
│
├── .github/workflows/
│   ├── ci.yml                         Every pull request
│   ├── deploy.yml                     Merge to main
│   └── evals.yml                      Weekly + manual trigger
│
└── docker-compose.yml                 Local full-stack testing
```

---

## Engineering decisions

**Chunking strategy.** Each card is split into five domain sections — overview, rewards, fees, insurance, eligibility — before embedding. A query about foreign transaction fees retrieves the `fees` chunk directly rather than competing against unrelated content inside a whole-document vector.

**Streaming architecture.** Claude outputs answer markdown followed by structured JSON (recommendations, citations), delimited by internal sentinels. The backend streams text token-by-token over SSE and holds the JSON sections until generation completes. The frontend renders the live text, then transitions to the full structured response on stream close.

**Evaluation design.** Ground-truth pairs were written by hand against the actual card data, not auto-generated. This ensures the eval tests correctness against human expectations rather than model self-consistency. The 5% regression threshold sits above LLM-judge noise (~2–3%) while catching real degradation from prompt, model, or data changes.

**Secret hygiene.** No credentials baked into images or committed to source control. Runtime secrets are injected via Lightsail environment configuration in production and GitHub Secrets in CI.

---

## Running locally

**Requirements:** Python 3.12 · Node.js 20 · Docker · API keys for OpenAI, Anthropic, Pinecone, LangSmith.

```bash
# Backend
cd backend
uv venv && .venv/Scripts/Activate.ps1
uv sync
python -m scripts.ingest          # populate Pinecone — run once
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
echo "NEXT_PUBLIC_BACKEND_URL=http://localhost:8000" > .env.local
npm run dev
```

```bash
# Unit tests — no API keys needed
pytest tests/unit/ -v

# Evaluation — Linux only, trigger from GitHub Actions
# Actions → RAG Quality Evals → Run workflow
```

---

## CI / CD

| Trigger | Steps |
|---|---|
| Pull request | `ruff` · `mypy` · `pytest` · `tsc` · `eslint` — 5 jobs in parallel |
| Merge to `main` | Build image → push to Lightsail → deploy to Vercel (~7 min) |
| Weekly + manual | RAGAS eval · fails on > 5% regression from baseline |

---

## Development Lifecycle

How the project was developed — from initial prototype to a continuously deployed production-ready system.
<img width="1536" height="1024" alt="ChatGPT Image May 12, 2026, 11_41_25 PM" src="https://github.com/user-attachments/assets/dbcde1d7-eae9-42ac-aec8-b72bf4252148" />

---

**Tarik Hasan**
