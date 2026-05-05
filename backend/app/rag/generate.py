"""Generate cited answers from retrieved chunks using Claude."""
import json
import uuid
from datetime import datetime, timezone

from app.clients.anthropic_client import generate_answer
from app.logging_config import get_logger
from app.models import AnswerResponse, CardRecommendation, Citation

log = get_logger(__name__)


SYSTEM_PROMPT = """You are CanCards AI, an expert assistant on Canadian credit cards.

Your job is to answer the user's question using ONLY the card information provided in the CONTEXT below. Never invent facts. If the context doesn't contain the answer, say so honestly.

Output a single JSON object matching this exact schema (no preamble, no code fences):
{
  "answer_markdown": "<your answer in markdown, conversational tone, 2-5 sentences>",
  "recommended_cards": [
    {
      "card_id": "<id from context>",
      "card_name": "<name from context>",
      "annual_fee_cad": <number>,
      "why": "<1-2 sentences why this card matches the user's need>",
      "key_benefits": ["<benefit 1>", "<benefit 2>", "<benefit 3>"]
    }
  ],
  "citations": [
    {
      "card_id": "<id>",
      "card_name": "<name>",
      "issuer": "<issuer>",
      "section": "<overview|rewards|fees|insurance|eligibility>"
    }
  ],
  "confidence_notes": "<optional short note about caveats, e.g. 'Verified as of 2026-05-04'>"
}

Rules:
- Recommend at most 3 cards, ranked best-first.
- Every recommended card MUST also appear in citations.
- Only mention cards that appear in the CONTEXT. Never make up cards.
- If the user's question can't be answered from the context, return an empty recommended_cards list and explain in answer_markdown.
- Keep answer_markdown concise.
"""


def build_user_prompt(question: str, chunks: list[dict]) -> str:
    """Build the user message with the retrieved context."""
    context_blocks = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk["metadata"]
        context_blocks.append(
            f"[{i}] card_id={meta['card_id']} | card_name={meta['card_name']} | "
            f"issuer={meta['issuer']} | section={meta['section']}\n"
            f"{meta['text']}\n"
        )
    context_str = "\n".join(context_blocks)
    return f"CONTEXT:\n{context_str}\n\nUSER QUESTION:\n{question}"


def parse_response(raw: str) -> AnswerResponse:
    """Parse the LLM's JSON output into a typed AnswerResponse."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
    data = json.loads(raw)
    return AnswerResponse(
        answer_markdown=data.get("answer_markdown", ""),
        recommended_cards=[CardRecommendation(**c) for c in data.get("recommended_cards", [])],
        citations=[Citation(**c) for c in data.get("citations", [])],
        confidence_notes=data.get("confidence_notes"),
        response_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
    )


async def generate_response(question: str, chunks: list[dict]) -> AnswerResponse:
    """Full generation pipeline: prompt build, LLM call, parse."""
    user_prompt = build_user_prompt(question, chunks)
    raw = await generate_answer(SYSTEM_PROMPT, user_prompt, max_tokens=2000)
    log.info("generated", chars=len(raw))
    try:
        return parse_response(raw)
    except (json.JSONDecodeError, ValueError) as e:
        log.error("parse_failed", error=str(e), raw=raw[:200])
        return AnswerResponse(
            answer_markdown=raw,
            recommended_cards=[],
            citations=[],
            confidence_notes="Parse error - showing raw response.",
            response_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
        )
