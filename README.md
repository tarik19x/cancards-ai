<div align="center">

# CanCards AI

### Ask about Canadian credit cards. Get straight answers, with sources.

Picking a credit card means wading through pages of fine print. CanCards AI reads it for you, answers in plain English, and shows exactly which document each answer came from. It also has a Credit Coach that estimates where your credit stands and tells you what to fix first.

<br>

<a href="https://cancards-ai.vercel.app">
  <img src="https://img.shields.io/badge/LIVE-DEMO-43B3AE?style=for-the-badge&logo=vercel&logoColor=white" />
</a>

</div>

---

## What it does

- **Ask.** Type a question the way you would say it out loud, like "Which card is best for groceries?" You get a short answer, the card it recommends, and the passages it was based on. It searches 50 Canadian cards and 76 official bank documents: cardholder agreements, benefit guides and insurance certificates.
- **Credit Coach.** A short chat that asks five questions about your credit habits, then gives you an estimated score, what is pulling it down, and what to fix first. Keep chatting afterwards ("How can I improve it fastest?") and it remembers the whole conversation, even if you refresh the page.
- **Browse and Compare.** Look through all 50 cards, open any card's details, or put two side by side.

One rule shapes the whole project: **the AI reads and writes, and ordinary code decides every number.** The coach's score is calculated by plain code, so the same answers always give the same score and no amount of arguing changes it. In Ask, the AI may only use the passages it was handed, and every answer lists its sources.

> The coach gives an estimate based on what you tell it. It is not a real credit score. For that, check Equifax or TransUnion.

---

## See it working

These screenshots were taken on the live site on 21 September 2026. The coach conversation uses invented details.

<p align="center">
  <img src="docs/screenshots/01-home.png" alt="CanCards AI home page with a question box" width="80%" />
</p>
<p align="center"><sub>The home page. Ask a question, or start from one of the suggestions.</sub></p>

<br>

<p align="center">
  <img src="docs/screenshots/02-ask-answer.png" alt="An answer about the TD Aeroplan Visa Infinite card, with a recommended card and sources" width="80%" />
</p>
<p align="center"><sub>Ask: "What is the annual fee on the TD Aeroplan Visa Infinite card, and what does it earn on groceries?" The answer, the recommended card, and the three sources it used. The panel on the right shows how many passages were read and how long it took.</sub></p>

<br>

<table>
  <tr>
    <td width="50%"><img src="docs/screenshots/03-browse-cards.png" alt="Browse page listing cards with fees and search filters" width="100%" /></td>
    <td width="50%"><img src="docs/screenshots/04-card-detail.png" alt="Detail page for the American Express Cobalt Card" width="100%" /></td>
  </tr>
  <tr>
    <td align="center"><sub>Browse all 50 cards. Search by name or filter by fee, network or perks.</sub></td>
    <td align="center"><sub>Every card has its own page: fees, rewards, who it suits and who it does not.</sub></td>
  </tr>
</table>

<br>

<p align="center">
  <img src="docs/screenshots/05-compare.png" alt="Side-by-side comparison of two American Express cards" width="80%" />
</p>
<p align="center"><sub>Compare any two cards side by side.</sub></p>

<br>

<p align="center">
  <img src="docs/screenshots/07-coach-start.png" alt="Credit Coach start screen" width="70%" />
</p>
<p align="center"><sub>Credit Coach: five questions, asked one at a time in plain conversation.</sub></p>

<br>

<p align="center">
  <img src="docs/screenshots/09-coach-score.png" alt="Credit Coach showing an estimated score of 87 with a breakdown by factor" width="55%" />
</p>
<p align="center"><sub>Once all five answers are in, the coach shows an estimate, what shaped it, and what to fix first.</sub></p>

<br>

<p align="center">
  <img src="docs/screenshots/10-coach-followup.png" alt="A follow-up answer that says balances under 10 percent would take the estimate from 87 to 93" width="55%" />
</p>
<p align="center"><sub>A follow-up. The 87 to 93 figure was worked out by the app's own scoring code. The AI only explains it.</sub></p>

---

## How it works

```mermaid
flowchart LR
    U["Your browser"] -->|"page files"| V["Vercel<br/>the website"]
    U -->|"questions and chat messages"| B["Backend on AWS Lightsail<br/>Python, in a Docker container"]
    B -->|"turns text into numbers"| O["OpenAI"]
    B -->|"finds matching passages"| P["Pinecone"]
    B -->|"reads and writes the text"| C["Claude"]
    B -->|"saves coach conversations"| N[("Neon PostgreSQL")]
```

The browser only downloads the website from Vercel. Every question and chat message goes straight to the backend, and only the backend talks to the other services.

### Ask, step by step

1. Your question is turned into a list of numbers that captures its meaning.
2. Two searches run at once: one finds passages with a similar meaning (Pinecone), the other finds passages that share the same words (a keyword search). Each returns its best 20.
3. The two lists are merged into roughly 34 different passages.
4. A second model, a reranker, reads each passage next to your question and puts them in a better order. The best 12 are kept.
5. Claude gets your question and only those 12 passages, and is told to answer from them and cite them. The answer appears on screen as it is written.

If the reranker is unavailable (it has a free monthly allowance), the app carries on with the merged order and pauses reranking for ten minutes.

**Where the 8,426 searchable pieces come from.** Each card has 5 short fact entries (50 cards, so 250 pieces). The bank PDFs, 75 of the 76 readable, are cut into pieces of about 1,000 characters that overlap by 150, so a sentence is never lost at a cut. That gives 8,176 more. One PDF had no readable text and is skipped. Every piece starts with its card's name, which turned out to matter a lot (see the results below).

### Credit Coach, step by step

```mermaid
flowchart LR
    A["Read the facts from the chat<br/>Claude"] --> B{"All 5 facts known?<br/>plain code"}
    B -->|"no"| C["Ask the next question"]
    B -->|"yes, first time"| D["Calculate the score<br/>plain code"]
    D --> E["Explain it in plain words<br/>Claude"]
    B -->|"yes, score already given"| F["Answer the follow-up<br/>Claude"]
```

- **Five facts, then a score.** Missed payments, how much of your credit limit you use, how long you have had credit, recent applications, and number of cards. Until all five are known the coach only asks questions and gives no advice.
- **The score is code, not AI.** It uses a simple scoring model I designed for this project. It is not the method the credit bureaus use.
- **Follow-ups use the same code.** Before Claude writes a word, the app works out what your score would be for each single change. In the screenshot above, keeping balances under 10% of your limit takes the estimate from 87 to 93. Claude is handed those numbers and told to use only those.
- **It remembers.** Each conversation is saved in PostgreSQL under a random ID that your browser keeps. Refresh the page, or restart the server, and the chat comes back. I checked this on the live site: a freshly started server returned a 16-message conversation it had never seen.
- **Words appear as they are written.** The coach first reads and scores your answers (about two seconds), then streams the reply.

---

## What I measured

The quality and speed numbers come from result files in `tests/evals/`. The cost figures come from a local usage log and the image size from a local Docker build, and neither of those is committed. The last column says what each number does and does not show.

| What | Result | How it was measured, and its limit |
|---|---|---|
| Finding the right passage | recall@8 rose from **0.32 to 0.96** | 100 held-out questions (95 with answers), written by me and locked before any tuning. The questions name their card, so this is the easier case. It measures search, not answer quality. |
| Coach gives advice too early | **98% to 0%** | 45 scripted conversations I wrote, run with and without the "all five facts" check. |
| Coach reads your facts correctly | **98% to 99.5%** (211 facts checked) | The same 45 conversations. |
| Coach gets the exact score right | **92.5% to 97.5%** | The same 45. Conversations that reach a score rose from 82% to 89%, in a median of 5 turns. |
| Attacks the coach resists | **47 of 50** on the first run, **50 of 50** after I fixed three real problems | 50 attack messages: prompt injection, secret extraction, score manipulation, forged turns, reading someone else's chat. Graded by code using hidden canary words, not by opinion. Covers the coach only, not Ask. |
| Speed with 15 people at once | first word in a median of **2.5 s**; **98%** under 3.8 s | One run of 105 requests, on my laptop, one server process. The full reply still takes 8 to 10 seconds. It is the first word that arrives quickly. |
| A speed bug the test found | median turn **10.6 s to 2.3 s** | Saving to the database after every step queued people behind each other. Saving once per turn fixed it. |
| Cost | **48% cheaper** ($1.00 to $0.52 on an identical benchmark), about **$0.03 per conversation** | Priced from the token counts the API reports, after adding prompt caching. One benchmark run. |
| Automated tests | **280+** backend tests | Plus two quality checks that replay recorded coach answers on every pull request at no cost. |
| Container size | about **200 MB**, against about 800 MB for a single-stage build | A comparison build I ran, not a before-and-after of this repo. |

**What the search results taught me.** These are the six configurations I tried on the 100 held-out questions:

| | Original text | With the card name added to every piece |
|---|---|---|
| Meaning search only | 0.32 | 0.83 |
| Plus keyword search | 0.44 | 0.82 |
| Plus reranker | 0.64 | **0.96** |

Adding the card name to every piece was the biggest gain, because most bank PDFs never say which card they belong to. The reranker helped as well. Keyword search added almost nothing once card names were in, so I do not count it as a win. It stays because it costs little and helps with exact terms.

---

## Design choices

- **Code decides the numbers.** The AI reads messy human sentences and writes friendly ones. Everything that has to be correct, the score and the what-if figures, comes from code that can be tested.
- **Measure before believing.** My first search test was too easy: plain vector search already scored about 0.95, which left no room to show any improvement. I wrote a harder one and used that instead.
- **Locked test questions.** The hard set of 200 questions is fingerprinted, and CI checks that nobody edited it after seeing the scores.
- **One save per turn.** My first guess at the slowdown was the database connection, and adding more connections changed nothing. Reading the library showed every save waits its turn, so the fix was fewer saves.
- **A database connection that heals itself.** Neon drops idle connections. The coach now tests a connection before using it and replaces a dead one, so a quiet spell no longer breaks the chat.
- **Measure cost, do not guess it.** My early cost estimates were about three times too low. A token-level cost meter showed 80% of spend was the same long instructions being re-sent, which prompt caching cut.

---

## Known limits

I would rather you read these here than find them yourself.

- The credit estimate rests on self-reported answers and illustrative weights. It is not a bureau score.
- The 45 conversations, 50 attacks and search questions are ones I wrote, not an independent test set.
- I measured search quality, not the quality of the written answers. A weekly RAGAS check exists, but its baseline is from May 2026, before the search rebuild.
- Attack testing covers the coach only. Ask has not been attack-tested.
- The replayed CI checks catch changes to my code and prompts. They cannot notice the AI model itself changing behaviour.
- The live site runs on one small server (AWS Lightsail Micro, 1 GB) with one worker. Fine for a demo, and a single point of failure.
- The hosted reranker has a free monthly allowance. If it runs out, Ask still works with less precise search.
- There are no user accounts. A conversation is found by a random ID stored in your browser, so clearing the browser starts a new chat.
- After a quiet spell the database is asleep, so the first message can be slower.

---

## Tech stack

| Layer | Technology |
|---|---|
| Website | Next.js 16 · React 19 · TypeScript · Tailwind CSS 4 · shadcn/ui |
| Backend | Python 3.12 · FastAPI · Pydantic |
| Language model | Anthropic Claude Sonnet 4.6 |
| Embeddings | OpenAI `text-embedding-3-small` (1,536 numbers per passage) |
| Search | Pinecone (vector search and hosted reranker) · BM25 keyword search |
| Coach workflow | LangGraph, six steps, with a plain-Python scorer |
| Conversation memory | PostgreSQL on Neon, through LangGraph's checkpointer |
| Tracing | LangSmith (optional) |
| Testing | pytest · ruff · mypy · tsc · ESLint · RAGAS (weekly) |
| Packaging and hosting | Docker (multi-stage) · AWS Lightsail (ca-central-1) · Vercel |
| CI / CD | GitHub Actions |

---

## Project structure

```
cancards-ai/
├── backend/
│   ├── app/
│   │   ├── clients/          Claude, OpenAI, Pinecone, and the token and cost meter
│   │   ├── rag/              Ask: chunking, search, reranking, answer generation, streaming
│   │   ├── coach/            Credit Coach
│   │   │   ├── graph.py        the six-step workflow
│   │   │   ├── profile.py      reads the five facts from the chat
│   │   │   ├── scoring.py      the score and the what-if figures (plain code)
│   │   │   ├── memory.py       saves conversations to PostgreSQL
│   │   │   └── stream.py       sends the reply word by word
│   │   ├── routers/          /api/ask, /api/coach, /api/cards, /health
│   │   ├── config.py         settings from environment variables
│   │   └── main.py           app entry point
│   ├── scripts/              building the search index, evaluation helpers
│   ├── tests/unit/           280+ tests, no outside services called
│   └── Dockerfile            multi-stage build
│
├── frontend/src/
│   ├── app/                  pages: Ask, Cards, Compare, Coach, Quiz, Settings
│   ├── components/           chat, cards, coach score card, layout
│   ├── hooks/                useStreamingChat, useCoachChat
│   └── lib/                  API clients, value calculator, quiz scoring
│
├── tests/evals/              search benchmark, 45 coach conversations, 50 attacks,
│                             load test, and all recorded results
├── docs/screenshots/         the images in this README
├── docker-compose.yml        a local PostgreSQL for development
└── .github/workflows/        ci.yml · deploy.yml · evals.yml
```

---

## Run it yourself

**You need:** Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 20 or newer, and API keys for OpenAI, Anthropic and Pinecone. Docker is optional (for a local database).

**1. Backend settings.** Create `backend/.env`:

```bash
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=cancards-index

# Optional: without it, coach chats are kept in memory and lost on restart
DATABASE_URL=postgresql://cancards:cancards@localhost:5432/cancards

# Set to false if you have no LangSmith key
LANGSMITH_TRACING=false
```

**2. Start the backend.**

```bash
docker compose up -d db          # optional: a local PostgreSQL for the coach
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

**3. Start the website** in a second terminal.

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_BACKEND_URL=http://localhost:8000" > .env.local
npm run dev
```

Open http://localhost:3000.

**Building the search index.** Ask needs a filled Pinecone index. The bank PDFs are copyrighted, so they are not in this repo and are downloaded by a script. Run these from `backend/`, in this order. Each script's opening comment lists its inputs and outputs.

```bash
uv run python -m scripts.fetch_documents          # download the PDFs
uv run python -m scripts.ingest                   # the 250 card fact entries
uv run python -m scripts.ingest_documents         # the PDFs
uv run python -m scripts.build_header_namespace   # the card-name version the app searches by default
```

**Tests.**

```bash
cd backend
uv run pytest                                                  # 280+ tests, no real keys needed
uv run python ../tests/evals/run_coach_scenarios.py --replay   # the 45 coach conversations, replayed
uv run python ../tests/evals/run_coach_attacks.py --replay     # the 50 attacks, replayed
```

---

## CI / CD

| When | What runs |
|---|---|
| Pull request | Six checks in parallel: ruff, mypy, pytest (with both replayed coach checks), tsc, ESLint, and a dependency-sync check |
| Merge to `main` | The full check suite, then build the Docker image, push it to Lightsail, wait until it is active, then deploy the website to Vercel. A failing check blocks the deploy. |
| Every Monday, or by hand | RAGAS answer-quality check, which fails on a drop of more than 5% from its baseline |

---

**Tarik Hasan**
