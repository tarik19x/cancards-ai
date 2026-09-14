"""Streaming RAG generation using Server-Sent Events."""

import json
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from app.clients.anthropic_client import stream_answer
from app.logging_config import get_logger
from app.models import AnswerResponse, CardRecommendation, Citation
from app.rag.generate import build_user_prompt

log = get_logger(__name__)

# A trailing comma before a closing brace/bracket is the one malformation Claude
# actually produces here. Losing every recommendation to it is a bad trade, so
# retry once with them stripped rather than dropping the whole section.
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")

CARDS_DELIMITER = "===CARDS==="
CITES_DELIMITER = "===CITES==="

STREAMING_SYSTEM_PROMPT = f"""You are CanCards AI, an expert on Canadian credit cards.

Answer the user's question using ONLY the card information in CONTEXT.
Be helpful and conversational.

Format your response in EXACTLY this structure:

1. Write your answer in markdown (2-5 clear sentences). Be specific and mention card names.

2. On its own line, write exactly: {CARDS_DELIMITER}

3. Write a JSON array of up to 3 recommended cards (or [] if none apply):
[
    {{
        "card_id": "<id>",
        "card_name": "<name>",
        "annual_fee_cad": <number>,
        "why": "<1-2 sentences>",
        "key_benefits": [
            "<benefit>",
            "<benefit>",
            "<benefit>"
        ]
    }}
]

4. On its own line, write exactly: {CITES_DELIMITER}

5. Write a JSON array of citations:
[{{"card_id":"<id>","card_name":"<name>","issuer":"<issuer>","section":"<overview|rewards|fees|insurance|eligibility>"}}]

Rules:
- Only include cards that appear in CONTEXT
- If no cards match, write your answer then {CARDS_DELIMITER} [] {CITES_DELIMITER} []
- Do not add any other delimiters or markers
"""


def parse_json_section(raw: str, section: str) -> list[Any]:
    """Parse one of the trailing JSON arrays. Returns [] if it can't be salvaged."""
    text = raw.strip() or "[]"
    try:
        return list(json.loads(text))
    except json.JSONDecodeError:
        pass

    try:
        parsed = list(json.loads(_TRAILING_COMMA.sub(r"\1", text)))
    except json.JSONDecodeError as e:
        log.warning("section_parse_failed", section=section, error=str(e), raw=text[:200])
        return []

    log.info("section_recovered", section=section, reason="trailing_comma")
    return parsed


async def stream_rag_response(question: str, chunks: list[dict]) -> AsyncIterator[str]:
    """Yield SSE events as Claude streams its response.

    The challenge: we want to stream the answer text but NOT the JSON sections.
    We accomplish this by buffering the last (delimiter_length) characters before
    yielding — that way we never accidentally yield part of CARDS_DELIMITER.
    """
    user_prompt = build_user_prompt(question, chunks)
    full_text = ""
    yielded_up_to = 0
    delimiter_pos = -1
    response_id = str(uuid.uuid4())

    try:
        async for token in stream_answer(STREAMING_SYSTEM_PROMPT, user_prompt, max_tokens=2000):
            full_text += token

            if delimiter_pos == -1:
                # We have not seen the delimiter yet
                pos = full_text.find(CARDS_DELIMITER)
                if pos != -1:
                    # Just found it — flush everything before the delimiter, then stop yielding text
                    delimiter_pos = pos
                    if pos > yielded_up_to:
                        new_text = full_text[yielded_up_to:pos]
                        yield f"data: {json.dumps({'type': 'token', 'content': new_text})}\n\n"
                        yielded_up_to = pos
                else:
                    # Yield up to (length - delimiter_len + 1). Anything in the trailing
                    # buffer might still be part of the delimiter.
                    safe_end = max(0, len(full_text) - len(CARDS_DELIMITER) + 1)
                    if safe_end > yielded_up_to:
                        new_text = full_text[yielded_up_to:safe_end]
                        yield f"data: {json.dumps({'type': 'token', 'content': new_text})}\n\n"
                        yielded_up_to = safe_end
            # else: delimiter found, accumulate but stop yielding text

        # Stream finished — parse the complete accumulated text
        if CARDS_DELIMITER in full_text:
            text_part, rest = full_text.split(CARDS_DELIMITER, 1)
        else:
            # Edge case: Claude never produced the delimiter (rare)
            text_part = full_text
            rest = ""

        if CITES_DELIMITER in rest:
            cards_str, cites_str = rest.split(CITES_DELIMITER, 1)
        else:
            cards_str = rest
            cites_str = "[]"

        # A card that fails validation is dropped on its own — one bad entry
        # shouldn't cost the user the other two.
        recommended_cards: list[CardRecommendation] = []
        for item in parse_json_section(cards_str, "cards"):
            try:
                recommended_cards.append(CardRecommendation(**item))
            except (TypeError, ValidationError) as e:
                log.warning("card_dropped", error=str(e), raw=str(item)[:100])

        citations: list[Citation] = []
        for item in parse_json_section(cites_str, "cites"):
            try:
                citations.append(Citation(**item))
            except (TypeError, ValidationError) as e:
                log.warning("citation_dropped", error=str(e), raw=str(item)[:100])

        response = AnswerResponse(
            answer_markdown=text_part.strip(),
            recommended_cards=recommended_cards,
            citations=citations,
            confidence_notes=None,
            response_id=response_id,
            timestamp=datetime.now(UTC),
        )

        # Final event with the complete response
        # Final event with the complete response.
        # chunks_used feeds the "Behind this answer" strip in the UI.
        response_dict = json.loads(response.model_dump_json())
        done_event = {
            "type": "done",
            "response": response_dict,
            "chunks_used": len(chunks),
        }
        yield f"data: {json.dumps(done_event)}\n\n"

    except Exception as e:
        log.error("stream_error", error=str(e), exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
