<div align="center">

# CanCards AI

Production-grade RAG system for Canadian credit card recommendations.

Natural language search, semantic retrieval, streaming responses, automated evaluation, and production deployment.

[Live Demo](https://cancards-ai.vercel.app)

</div>

---

## Overview

CanCards AI is a Retrieval-Augmented Generation (RAG) application that answers questions about Canadian credit cards using semantic search and grounded LLM generation.

The system retrieves relevant card information from a vector database, generates cited responses with Claude Sonnet, and continuously evaluates output quality using RAGAS.

Built to demonstrate practical AI engineering skills across:

- RAG pipeline design
- LLM evaluation
- streaming architectures
- production deployment
- CI/CD automation
- observability and testing

---

## System Flow

```text
                USER QUESTION

                       ↓

        ┌────────────────────────┐
        │   Claude RAG System    │
        │    (main chatbot)      │
        └────────────────────────┘

                       ↓

             GENERATED ANSWER

                       ↓

        ┌────────────────────────┐
        │  GPT-4o-mini Judge LLM │
        │   (RAGAS evaluator)    │
        └────────────────────────┘

                       ↓

                   SCORES
```

---

## Architecture

## System Architecture & Evaluation Flow

```text
┌──────────────────────────────────────────────────────────────┐
│                           USER                              │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────┐
                    │  Next.js Client  │
                    │     (Vercel)     │
                    └────────┬─────────┘
                             │
                       Streaming (SSE)
                             │
                             ▼
                    ┌──────────────────┐
                    │ FastAPI Backend  │
                    │ (AWS Lightsail)  │
                    └────────┬─────────┘
                             │
         ┌───────────────────┼────────────────────┐
         │                   │                    │
         ▼                   ▼                    ▼

   ┌──────────┐       ┌──────────┐        ┌─────────────┐
   │  OpenAI  │       │ Pinecone │        │   Claude    │
   │Embedding │──────▶│  Vector  │───────▶│   Sonnet    │
   │  Model   │       │   Store  │        │ Generation  │
   └──────────┘       └──────────┘        └──────┬──────┘
                                                  │
                                                  ▼

                                         GENERATED ANSWER
                                                  │
                                                  ▼

                                  ┌────────────────────────┐
                                  │  GPT-4o-mini Judge LLM │
                                  │   RAGAS Evaluation     │
                                  └──────────┬─────────────┘
                                             │
                         ┌───────────────────┼───────────────────┐
                         │                   │                   │
                         ▼                   ▼                   ▼

                 Faithfulness        Context Precision      Answer Quality
                      Scores                 Scores               Scores


                                                  │
                                                  ▼

                                         ┌────────────┐
                                         │ LangSmith  │
                                         │  Tracing   │
                                         └────────────┘
```

---

## Features

| Feature | Details |
|---|---|
| Semantic Retrieval | OpenAI embeddings + Pinecone vector search |
| Grounded Responses | Claude Sonnet with citation-aware generation |
| Streaming Chat | Token streaming with Server-Sent Events |
| Automated Evaluation | RAGAS regression testing with judge LLM |
| Observability | Full tracing and prompt inspection via LangSmith |
| CI/CD | Automated testing and deployment with GitHub Actions |
| Type Safety | Strict TypeScript, Pydantic v2, mypy, ESLint |

---

## Tech Stack

### Frontend
- Next.js 15
- TypeScript
- Tailwind CSS
- shadcn/ui

### Backend
- FastAPI
- Python 3.12
- Pydantic v2
- Uvicorn

### AI / ML
- Claude Sonnet
- OpenAI Embeddings
- LangChain
- RAGAS
- LangSmith

### Infrastructure
- Pinecone
- Docker
- AWS Lightsail
- Vercel
- GitHub Actions

---

## Project Structure

```text
cancards-ai/
│
├── backend/
│   ├── app/
│   │   ├── clients/          External API clients
│   │   ├── rag/              Retrieval + generation pipeline
│   │   ├── routers/          API endpoints
│   │   ├── models.py
│   │   ├── config.py
│   │   └── main.py
│   │
│   ├── data/
│   │   └── cards.json
│   │
│   ├── tests/
│   │   ├── unit/
│   │   └── evals/
│   │
│   ├── Dockerfile
│   └── pyproject.toml
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── lib/
│   │   └── types/
│   │
│   ├── package.json
│   └── tsconfig.json
│
├── .github/
│   └── workflows/
│
├── docker-compose.yml
└── README.md
```

---

## Evaluation Pipeline

The project includes a dedicated RAG evaluation workflow using RAGAS.

- 30 curated ground-truth Q&A pairs
- automated regression testing
- faithfulness and context precision scoring
- CI failure on significant quality degradation

This helps validate retrieval quality and reduce hallucinations during development.

---

## Local Setup

### Prerequisites

- Python 3.12
- Node.js 20+
- Docker Desktop
- OpenAI API key
- Anthropic API key
- Pinecone account

---

### Backend

```bash
cd backend

uv venv
uv sync

python -m scripts.ingest

uvicorn app.main:app --reload --port 8000
```

---

### Frontend

```bash
cd frontend

npm install
npm run dev
```

---

## Testing

```bash
# Backend tests
pytest tests/unit/ -v
```

---

## CI/CD

| Workflow | Purpose |
|---|---|
| `ci.yml` | Linting, type checking, unit tests |
| `deploy.yml` | Production deployment |
| `evals.yml` | Automated RAG quality evaluation |

---

## Engineering Focus

This project emphasizes practical AI engineering rather than prototype-only development.

Key areas include:

- retrieval quality
- structured LLM output
- streaming architectures
- evaluation pipelines
- defensive parsing
- observability
- deployment reliability
- typed backend systems

---

## Author

**Tarik Hasan**
---

## License

MIT
