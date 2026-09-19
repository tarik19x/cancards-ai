"""Generate point-1 sub-step 1j's hard eval questions.

Point 1i's finding: the existing 60 questions can't show retrieval improving,
because they're built from cards.json and answered by chunks also built from
cards.json -- question and answer share the same words, so every method
scores ~99%. This script instead drafts questions from the real PDF corpus,
in the failure shapes 1h actually found:

- exact_term: a chunk states a specific $ amount, %, or day count. The
  question must be answered with that exact figure, not a paraphrase.
- exclusion: a chunk describes what's NOT covered or when a rule stops
  applying.
- disambiguation: two different cards' PDFs contain near-identical wording
  (point 1h's real cause -- e.g. Brim's claim-limit clause vs RBC WestJet's).
  The question names one specific card; only that card's own chunk is a
  correct answer, even though a near-twin sits under another card's id.
- cross_source: needs one fact from cards.json and one fact from that same
  card's PDF, joined in one question.
- unanswerable: hand-written, no matching chunk exists at all -- checked
  against cards.json below, not sampled from the corpus.

Which chunks become candidates is decided by regex/keyword matching and a
stable hash of the chunk id (see _stable_rank) -- never by how well or badly
a retriever finds them. Picking questions by retrieval outcome is exactly
what point 1's rules forbid.

An LLM (the same Claude model the app itself calls) drafts the question and
ground_truth from each candidate chunk. Grounding is checked automatically
before a question is kept: the $/%/day figures in ground_truth must actually
appear in the source chunk. That catches hallucinated numbers; it does not
catch an awkwardly-phrased question, which is what the human sample-check
(1j) is for.

This is a REVIEW pass, not the final set: it writes candidates to
tests/evals/hard_questions_review.json, never touching ground_truth.json.
Tarik reviews the sample; only after that does a separate step (not this
script) merge an approved batch into ground_truth.json with eval_set="hard"
and a practice/final split.

Run with (from backend/):
  uv run python -m scripts.generate_hard_eval_questions --per-category 4
"""

import argparse
import asyncio
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.clients.anthropic_client import generate_answer as _generate_answer_uncached
from app.logging_config import configure_logging, get_logger
from app.models import Card
from app.rag.bm25_index import Bm25Corpus, enable_disk_cache, get_bm25_corpus
from scripts.llm_cache import BudgetExceeded, CachedGenerator

configure_logging("WARNING")
log = get_logger(__name__)

# Every draft and check below goes through this, so reruns only pay for
# prompts that actually changed.
generate_answer = CachedGenerator(_generate_answer_uncached)

CARDS_PATH = Path(__file__).resolve().parents[1] / "data" / "cards.json"
CORPUS_CACHE_PATH = Path(__file__).resolve().parents[1] / "data" / "cache" / "corpus.json"
REVIEW_PATH = Path(__file__).resolve().parents[2] / "tests" / "evals" / "hard_questions_review.json"

PDF_DOC_TYPES = {"cardholder_agreement", "benefit_guide", "insurance_certificate"}

MONEY_RE = re.compile(r"\$[\d,]+(?:\.\d+)?")
PERCENT_RE = re.compile(r"\d+(?:\.\d+)?%")
DAYS_RE = re.compile(r"\b\d+\s*(?:consecutive\s+)?days?\b", re.I)
EXCLUSION_PHRASES = [
    "does not cover",
    "not covered",
    "will not pay",
    "is excluded",
    "not eligible",
    "does not apply",
    "no coverage",
]

Chunk = tuple[str, dict[str, Any]]  # (chunk_id, metadata)


def _stable_rank(key: str) -> int:
    """Deterministic ordering that has nothing to do with retrieval quality --
    so "the first N candidates" never quietly means "the N easiest (or
    hardest) for search to find", which would bias the benchmark by
    construction.
    """
    return int(hashlib.sha256(key.encode()).hexdigest(), 16)


def pdf_chunks(corpus: Bm25Corpus) -> list[Chunk]:
    """Every chunk sourced from a real PDF, as opposed to a cards.json summary."""
    return [
        (cid, meta)
        for cid, meta in zip(corpus.ids, corpus.metadatas)
        if meta.get("doc_type") in PDF_DOC_TYPES
    ]


def find_exact_term_candidates(chunks: list[Chunk]) -> list[tuple[str, dict, list[str]]]:
    """Chunks stating a specific figure -- the fact a paraphrase can't fake."""
    out = []
    for cid, meta in chunks:
        text = meta.get("text", "")
        facts = MONEY_RE.findall(text) + PERCENT_RE.findall(text) + DAYS_RE.findall(text)
        if facts:
            out.append((cid, meta, facts))
    out.sort(key=lambda t: _stable_rank(t[0]))
    return out


def find_exclusion_candidates(chunks: list[Chunk]) -> list[Chunk]:
    out = [
        (cid, meta)
        for cid, meta in chunks
        if any(p in meta.get("text", "").lower() for p in EXCLUSION_PHRASES)
    ]
    out.sort(key=lambda t: _stable_rank(t[0]))
    return out


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _mentions_own_card(text: str, card_name: str) -> bool:
    """True if the chunk names its own card -- disqualifying it from
    disambiguation, whose entire premise is a clause that identifies
    NEITHER card (point 1h's actual finding). Some shared legal boilerplate
    (e.g. a table of contents naming every product covered by one agreement)
    does mention the card by name even though the wording is otherwise
    near-identical to another card's document; those aren't a fair trap.
    """
    clean = re.sub(r"[®™©]", "", card_name).strip().lower()
    return bool(clean) and clean in re.sub(r"[®™©]", "", text).lower()


def find_disambiguation_candidates(
    chunks: list[Chunk], min_jaccard: float = 0.6
) -> list[tuple[Chunk, Chunk, float]]:
    """Pairs of chunks from different cards' documents with near-identical
    wording -- point 1h's actual cause: the shared clause names neither card,
    so a question naming one card can't be told apart from its twin by text
    alone. Bucketed by (doc_type, text length // 50) to avoid an O(n^2) scan
    over the full 8k-chunk corpus.
    """
    nameless = [
        (cid, meta)
        for cid, meta in chunks
        if not _mentions_own_card(meta.get("text", ""), meta.get("card_name", ""))
    ]
    buckets: dict[tuple[str, int], list[tuple[str, dict, set[str]]]] = defaultdict(list)
    for cid, meta in nameless:
        text = meta.get("text", "")
        buckets[(meta.get("doc_type", ""), len(text) // 50)].append((cid, meta, _tokens(text)))

    pairs: list[tuple[Chunk, Chunk, float]] = []
    for bucket in buckets.values():
        for i in range(len(bucket)):
            cid_a, meta_a, tok_a = bucket[i]
            if not tok_a:
                continue
            for j in range(i + 1, len(bucket)):
                cid_b, meta_b, tok_b = bucket[j]
                if meta_a.get("card_id") == meta_b.get("card_id") or not tok_b:
                    continue
                jaccard = len(tok_a & tok_b) / len(tok_a | tok_b)
                if jaccard >= min_jaccard:
                    pairs.append(((cid_a, meta_a), (cid_b, meta_b), jaccard))
    pairs.sort(key=lambda t: _stable_rank(t[0][0] + t[1][0]))
    # A clause shared by three cards yields two pairs with the same target
    # chunk, which the builder would turn into two identical questions (seen
    # for Amex Platinum's chunk 16 against Gold and Cobalt). One trap per
    # target is enough.
    seen_targets: set[str] = set()
    unique: list[tuple[Chunk, Chunk, float]] = []
    for pair in pairs:
        if pair[0][0] not in seen_targets:
            seen_targets.add(pair[0][0])
            unique.append(pair)
    return unique


def find_cross_source_candidates(
    chunks: list[Chunk], cards_by_id: dict[str, Card]
) -> list[tuple[str, dict, list[str], Card]]:
    """A PDF chunk with a specific figure, paired with its own card's
    cards.json record -- the question needs both sources to answer.
    """
    exact = find_exact_term_candidates(chunks)
    out = []
    for cid, meta, facts in exact:
        card = cards_by_id.get(meta.get("card_id", ""))
        if card is not None:
            out.append((cid, meta, facts, card))
    return out


def _extract_facts(text: str) -> set[str]:
    return set(MONEY_RE.findall(text)) | set(PERCENT_RE.findall(text)) | set(DAYS_RE.findall(text))


def _grounded(ground_truth: str, source_text: str) -> bool:
    """A generated answer is grounded only if at least one $/%/day figure it
    states also appears verbatim in the source chunk -- catches an LLM
    inventing or misreading a number. It does not catch a badly-phrased
    question; that's what the human sample-check in 1j is for.
    """
    source_facts = _extract_facts(source_text)
    if not source_facts:
        return True  # nothing numeric to check (e.g. an exclusion question)
    answer_facts = _extract_facts(ground_truth)
    return bool(source_facts & answer_facts)


_SENTENCE_END = re.compile(r"[.!?][\"')\]]?(?:\s|$)")
MIN_TRIMMED_CHARS = 80


def _complete_sentences(text: str) -> str:
    """Drop the partial sentence at each end of a 1000-character chunk.

    Telling the model not to finish a cut-off sentence wasn't enough: in the
    third judged batch it silently left off the last word of an unfinished
    definition and presented the rest as complete. Not showing it the
    fragment removes the choice. Only ever removes text, so it can't add a
    claim; an over-eager cut at an abbreviation just means less to draft from.
    """
    text = text.strip()
    ends = list(_SENTENCE_END.finditer(text))
    if not ends:
        return ""
    body = text[: ends[-1].end()].strip()
    # A lowercase first character means the chunk started mid-sentence.
    if not re.match(r"[A-Z0-9(\"“]", body):
        first = _SENTENCE_END.search(body)
        body = body[first.end() :] if first else ""
    return body.strip()


DRAFT_SYSTEM_PROMPT = """You write test questions for a document retrieval system, from one \
paragraph of a Canadian credit card's {doc_type_label} document.

Write ONE specific, realistic question a cardholder might ask, answerable using ONLY this \
paragraph -- name the specific card in the question, and refer to the document only as a \
"{doc_type_label}" if you refer to it at all -- never guess a different document type. Write \
the ground_truth answer using only facts stated in the paragraph; never add anything the \
paragraph doesn't say.

This paragraph is a short excerpt and may start or end mid-sentence. If a sentence is cut off, \
do not guess, complete, or imply how it continues -- build the question and answer only around \
what's fully written. If the paragraph uses a general term (e.g. "travelling expenses"), do \
not narrow it to a specific example (e.g. "meals") unless that example is named in the text. \
If a figure is marked as an estimate, illustration, minimum, or maximum, keep that qualifier in \
ground_truth rather than stating it as a plain fact. If the paragraph names a specific term (e.g. \
"deductible"), don't restate it as a broader claim (e.g. "your total out-of-pocket cost") unless \
the paragraph itself says they're the same -- a cap or exclusion stated elsewhere could make them \
different. If you write a yes/no question, it must ask about exactly what the paragraph settles: \
never use wider wording such as "anything extra", "any charges" or "always" when the paragraph \
only covers one thing (e.g. interest on new purchases), and never answer yes or no to a claim \
wider than what the paragraph states.

{style_instruction}

Return ONLY JSON, no markdown fence: {{"question": "...", "ground_truth": "..."}}"""

DOC_TYPE_LABELS = {
    "cardholder_agreement": "cardholder agreement",
    "benefit_guide": "benefit guide",
    "insurance_certificate": "certificate of insurance",
}

STYLE_EXACT = "Ask for the specific figure directly."
STYLE_PARAPHRASE = (
    "Describe the situation in your own words, as a real person would -- do not reuse any "
    "distinctive noun, phrase, or heading from the paragraph (e.g. if the paragraph is headed "
    "'Travel Medical Insurance', don't ask about 'travel medical insurance'; describe the "
    "situation instead). The ground_truth still uses the paragraph's exact figures."
)
STYLE_EXCLUSION = (
    "Ask what is excluded, or under what condition the coverage or rule stops applying. If the "
    "paragraph is actually about how this insurance coordinates with other insurance (e.g. "
    "'excess' or 'non-contributory' coverage) rather than a true exclusion, phrase the question "
    "around that coordination rule accurately -- don't call it an exclusion or a stop-condition."
)


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    """Claude occasionally answers with reasoning text wrapped around the
    JSON object despite being told not to. Pull out the object rather than
    discarding the whole (paid-for) response over stray prose around it.
    """
    text = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def draft_question(
    card_name: str,
    chunk_text: str,
    style: str,
    doc_type: str = "cardholder_agreement",
    feedback: str | None = None,
) -> dict[str, str] | None:
    chunk_text = _complete_sentences(chunk_text)
    if len(chunk_text) < MIN_TRIMMED_CHARS:
        return None
    prompt = DRAFT_SYSTEM_PROMPT.format(
        style_instruction=style, doc_type_label=DOC_TYPE_LABELS.get(doc_type, doc_type)
    )
    user_prompt = f'Card: {card_name}\n\nParagraph:\n"""\n{chunk_text}\n"""'
    if feedback:
        user_prompt += f"\n\n{feedback}"
    raw = await generate_answer(prompt, user_prompt, max_tokens=400)
    parsed = _parse_json_object(raw)
    if parsed is None or "question" not in parsed or "ground_truth" not in parsed:
        log.warning("draft_question_parse_failed", raw=raw[:200])
        return None
    return {"question": parsed["question"], "ground_truth": parsed["ground_truth"]}


_STOPWORDS = {
    "the", "and", "for", "are", "you", "your", "this", "that", "with", "from",
    "have", "will", "under", "when", "what", "does", "how", "much", "many",
    "per", "any", "all", "not", "can", "get", "into", "which", "who",
}  # fmt: skip


def _content_words(text: str) -> list[str]:
    return re.findall(r"[a-z]{3,}", text.lower())


def _shared_bigrams(question: str, source_text: str, card_name: str) -> set[str]:
    """Exact two-word phrases the drafted question shares with the source
    paragraph -- catches a 'paraphrase' that quietly reuses the paragraph's
    own wording (e.g. a heading like "Travel Medical Insurance" echoed back
    almost verbatim). Bigrams made only of short/generic words, or that
    overlap the card's own name (which the question must name anyway), don't
    count.
    """
    card_words = set(_content_words(card_name))

    def bigrams(text: str) -> set[str]:
        words = [w for w in _content_words(text) if w not in card_words]
        return {
            f"{a} {b}"
            for a, b in zip(words, words[1:])
            if a not in _STOPWORDS or b not in _STOPWORDS
        }

    return bigrams(question) & bigrams(source_text)


DISTRACTOR_CHECK_SYSTEM = (
    "You check whether a paragraph, on its own, answers a question the same way as a given "
    "expected answer, with nothing else provided. The paragraph comes from a different card's "
    "document on purpose, so ignore which card, bank or product the question names and judge "
    "only whether the paragraph's content gives the same answer. Answer with exactly one word: "
    "YES or NO."
)


async def _distractor_also_answers(question: str, ground_truth: str, distractor_text: str) -> bool:
    """Point 1h's finding generalized: some near-duplicate paragraphs are
    near-duplicates because the fact really is boilerplate shared across
    cards (a shared insurer's phone number, standard agreement language), not
    because they happen to look similar. If the distractor paragraph alone
    would also answer the question the same way, it can't actually tell the
    two cards apart and isn't a fair disambiguation test.

    Asks about the question, not just the claim: the claim usually carries
    card-specific wording ("As a Visa Infinite cardholder...") that a twin
    paragraph lacks, so a claim-only check said NO for a twin that still
    answered the question identically (TD First Class vs TD Cash Back).
    """
    user_prompt = (
        f"Question: {question}\n"
        f"Expected answer: {ground_truth}\n\n"
        f'Paragraph:\n"""\n{distractor_text}\n"""\n\n'
        "Using this paragraph alone, would the question get the same answer?"
    )
    raw = await generate_answer(DISTRACTOR_CHECK_SYSTEM, user_prompt, max_tokens=5)
    return raw.strip().upper().startswith("Y")


def _progress(category: str, done: int, total: int) -> None:
    if done % 10 == 0 or done == total:
        print(
            f"  {category}: {done}/{total} (paid calls so far: {generate_answer.calls_made})",
            flush=True,
        )


async def build_exact_term(
    chunks: list[Chunk],
    n: int,
    claimed: set[str] | None = None,
    results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """`claimed` is shared across categories: one paragraph backs one question,
    so the same text can't land on both sides of the practice/final split.
    """
    claimed = claimed if claimed is not None else set()
    candidates = find_exact_term_candidates(chunks)
    # The caller's list, so a spending stop mid-loop keeps what was drafted.
    results = results if results is not None else []
    for cid, meta, _facts in candidates:
        if len(results) >= n:
            break
        if cid in claimed:
            continue
        drafted = await draft_question(
            meta["card_name"], meta["text"], STYLE_EXACT, meta.get("doc_type", "")
        )
        if drafted and _grounded(drafted["ground_truth"], meta["text"]):
            claimed.add(cid)
            results.append(
                {
                    **drafted,
                    "relevant_card_ids": [meta["card_id"]],
                    "answering_chunk_ids": [cid],
                    "question_type": "exact_term",
                }
            )
            _progress("exact_term", len(results), n)
    return results


async def build_paraphrase(
    chunks: list[Chunk],
    n: int,
    claimed: set[str] | None = None,
    results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    claimed = claimed if claimed is not None else set()
    # Different stable slice than exact_term (offset by reversing) so the two
    # categories don't draft from the identical chunks.
    candidates = list(reversed(find_exact_term_candidates(chunks)))
    # The caller's list, so a spending stop mid-loop keeps what was drafted.
    results = results if results is not None else []
    for cid, meta, _facts in candidates:
        if len(results) >= n:
            break
        if cid in claimed:
            continue
        doc_type = meta.get("doc_type", "")
        drafted = await draft_question(meta["card_name"], meta["text"], STYLE_PARAPHRASE, doc_type)
        if not drafted or not _grounded(drafted["ground_truth"], meta["text"]):
            continue
        shared = _shared_bigrams(drafted["question"], meta["text"], meta["card_name"])
        if shared:
            # One retry, telling the model exactly which phrase(s) gave it
            # away, rather than silently keeping a paraphrase that isn't one.
            retry = await draft_question(
                meta["card_name"],
                meta["text"],
                STYLE_PARAPHRASE,
                doc_type,
                feedback=(
                    "Your previous attempt repeated these exact phrases from the paragraph: "
                    f"{', '.join(sorted(shared))}. Rewrite the question without them."
                ),
            )
            if (
                retry
                and _grounded(retry["ground_truth"], meta["text"])
                and not _shared_bigrams(retry["question"], meta["text"], meta["card_name"])
            ):
                drafted = retry
            else:
                continue  # still echoing source wording after one retry -- skip this candidate
        claimed.add(cid)
        results.append(
            {
                **drafted,
                "relevant_card_ids": [meta["card_id"]],
                "answering_chunk_ids": [cid],
                "question_type": "paraphrase",
            }
        )
        _progress("paraphrase", len(results), n)
    return results


async def build_exclusion(
    chunks: list[Chunk],
    n: int,
    claimed: set[str] | None = None,
    results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    claimed = claimed if claimed is not None else set()
    candidates = find_exclusion_candidates(chunks)
    # The caller's list, so a spending stop mid-loop keeps what was drafted.
    results = results if results is not None else []
    for cid, meta in candidates:
        if len(results) >= n:
            break
        if cid in claimed:
            continue
        drafted = await draft_question(
            meta["card_name"], meta["text"], STYLE_EXCLUSION, meta.get("doc_type", "")
        )
        if drafted:
            claimed.add(cid)
            results.append(
                {
                    **drafted,
                    "relevant_card_ids": [meta["card_id"]],
                    "answering_chunk_ids": [cid],
                    "question_type": "exclusion",
                }
            )
            _progress("exclusion", len(results), n)
    return results


async def build_disambiguation(
    chunks: list[Chunk],
    n: int,
    claimed: set[str] | None = None,
    results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Question names the target card; only its own chunk counts as correct
    -- the near-identical twin under another card's document is a distractor,
    per 1i's labelling rule, never a second right answer.
    """
    claimed = claimed if claimed is not None else set()
    pairs = find_disambiguation_candidates(chunks)
    # The caller's list, so a spending stop mid-loop keeps what was drafted.
    results = results if results is not None else []
    for (cid_a, meta_a), (cid_b, meta_b), jaccard in pairs:
        if len(results) >= n:
            break
        if cid_a in claimed:
            continue
        drafted = await draft_question(
            meta_a["card_name"], meta_a["text"], STYLE_EXACT, meta_a.get("doc_type", "")
        )
        if not drafted or not _grounded(drafted["ground_truth"], meta_a["text"]):
            continue
        # A high text-similarity score alone doesn't make a fair trap: some
        # near-duplicates are near-duplicates because the fact really is
        # shared boilerplate (a shared insurer's phone number, standard
        # agreement language), in which case the distractor answers just as
        # well and the question can't actually distinguish the two cards.
        if await _distractor_also_answers(
            drafted["question"], drafted["ground_truth"], meta_b["text"]
        ):
            continue
        claimed.add(cid_a)
        results.append(
            {
                **drafted,
                "relevant_card_ids": [meta_a["card_id"]],
                "answering_chunk_ids": [cid_a],
                "question_type": "disambiguation",
                "distractor_chunk_id": cid_b,  # documents the trap; not a correct answer
                "distractor_jaccard": round(jaccard, 2),
            }
        )
        _progress("disambiguation", len(results), n)
    return results


CROSS_SOURCE_SYSTEM_PROMPT = """You write test questions for a document retrieval system. The \
question must need TWO different facts about the SAME credit card to answer, used together in \
one combined requirement -- never two separate facts just asked back to back with "and".

You are given: this card's real annual fee, and one paragraph from its {doc_type_label} \
containing a specific figure (a dollar amount, a percentage, or a day count).

Only use the paragraph's figure if it's a benefit level with an obvious direction of "better" \
for a cardholder -- a coverage cap, reimbursement limit, protection duration, or reward rate \
(higher is better), or a fee or deductible (lower is better). If the figure is an operational \
cutoff or condition where it's not obviously better for the cardholder to have it higher or \
lower (e.g. a balance threshold that changes how often a statement is mailed), do not use it --\
reply with {{"question": null, "ground_truth": null}} instead.

Otherwise, write ONE question shaped like: "Would the {{card_name}} suit someone who needs both \
an annual fee under $X and [a specific, concrete condition based on the paragraph]?" Pick X a \
little above the real fee, so the real fee clearly qualifies. Pick the paragraph-based threshold \
so the real figure clearly satisfies it too, in the direction that's actually better for the \
cardholder. The condition must require the paragraph's actual figure to check, not just restate \
the paragraph's topic.

Then write ground_truth: start with "Yes,", then give ONLY the two real figures (the exact fee \
and the exact paragraph figure) as plain facts -- do not restate the question's own made-up \
threshold (the $X or the specific condition you chose), even to compare against it. State no \
number that isn't the real fee or the real paragraph figure.

Return ONLY the JSON object, nothing before or after it, no markdown fence, no explanation of \
your reasoning either way: {{"question": "...", "ground_truth": "..."}}"""


async def draft_cross_source_question(
    card: Card, chunk_text: str, doc_type: str
) -> dict[str, str] | None:
    chunk_text = _complete_sentences(chunk_text)
    if len(chunk_text) < MIN_TRIMMED_CHARS:
        return None
    prompt = CROSS_SOURCE_SYSTEM_PROMPT.format(
        doc_type_label=DOC_TYPE_LABELS.get(doc_type, doc_type)
    )
    user_prompt = (
        f"Card: {card.name}\nReal annual fee: ${card.annual_fee_cad:,.2f} CAD\n\n"
        f'Paragraph:\n"""\n{chunk_text}\n"""'
    )
    raw = await generate_answer(prompt, user_prompt, max_tokens=400)
    parsed = _parse_json_object(raw)
    if parsed is None or "question" not in parsed or "ground_truth" not in parsed:
        log.warning("draft_cross_source_question_parse_failed", raw=raw[:200])
        return None
    if parsed["question"] is None:  # the figure had no clear "better" direction
        return None
    return {"question": parsed["question"], "ground_truth": parsed["ground_truth"]}


def _cross_source_grounded(ground_truth: str, annual_fee_cad: float, chunk_text: str) -> bool:
    """Both real figures -- the fee and the paragraph's own figure -- must
    appear in the answer, and nothing else numeric may: an external review
    caught the model restating the question's own made-up comparison
    threshold ("under $150 CAD") inside ground_truth, which isn't a number
    either real source actually states, however arithmetically consistent
    it happens to be with them.
    """
    fee_str = f"${annual_fee_cad:,.2f}"
    chunk_facts = _extract_facts(chunk_text)
    answer_facts = _extract_facts(ground_truth)
    has_required = fee_str in ground_truth and bool(chunk_facts & answer_facts)
    no_extra_numbers = answer_facts <= (chunk_facts | {fee_str})
    return has_required and no_extra_numbers


async def build_cross_source(
    chunks: list[Chunk],
    cards_by_id: dict[str, Card],
    n: int,
    claimed: set[str] | None = None,
    results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    claimed = claimed if claimed is not None else set()
    candidates = find_cross_source_candidates(chunks, cards_by_id)
    # The caller's list, so a spending stop mid-loop keeps what was drafted.
    results = results if results is not None else []
    # One question per card: every cross_source question also needs that
    # card's fee chunk, and repeating it would put the same fee chunk on both
    # sides of the split.
    used_cards: set[str] = set()
    for cid, meta, _facts, card in candidates:
        if len(results) >= n:
            break
        if cid in claimed or card.card_id in used_cards:
            continue
        drafted = await draft_cross_source_question(card, meta["text"], meta.get("doc_type", ""))
        if not drafted or not _cross_source_grounded(
            drafted["ground_truth"], card.annual_fee_cad, meta["text"]
        ):
            continue
        claimed.add(cid)
        used_cards.add(card.card_id)
        results.append(
            {
                **drafted,
                "relevant_card_ids": [card.card_id],
                "answering_chunk_ids": [f"{card.card_id}::fees", cid],
                "question_type": "cross_source",
            }
        )
        _progress("cross_source", len(results), n)
    return results


# Hand-written: no matching content exists anywhere in the corpus. Each entry
# is checked below against cards.json so an "unanswerable" question doesn't
# silently become answerable after a future card is added.
UNANSWERABLE_SPECS: list[tuple[str, str]] = [
    (
        "Does the RBC Avion Visa Infinite offer a Bitcoin or crypto cashback rewards option?",
        "no_reward_category:crypto",
    ),
    (
        "What is the annual fee on the American Express Platinum Card's US-dollar variant?",
        "no_card_id:amex-platinum-usd",
    ),
    (
        "Does the CIBC Costco Mastercard include a free companion airline ticket benefit?",
        "no_insurance_field:companion_ticket",
    ),
    (
        "What is the minimum credit score required for the Tangerine Money-Back Credit Card "
        "issued in Quebec under provincial rules?",
        "no_field:quebec_specific_score",
    ),
    (
        "Does the Brim World Elite Mastercard charge a fee for balance transfers from a "
        "different currency?",
        "no_field:balance_transfer_fx_fee",
    ),
    (
        "What is the crypto staking reward rate on the Neo Mastercard?",
        "no_reward_category:crypto_staking",
    ),
    (
        "Does the Scotiabank Passport Visa Infinite offer NFT purchase protection?",
        "no_insurance_field:nft_protection",
    ),
    (
        "What is the private jet charter discount on the TD First Class Travel Visa Infinite?",
        "no_field:private_jet_discount",
    ),
    (
        "Does the PC Insiders World Elite Mastercard offer a home insurance discount?",
        "no_field:home_insurance_discount",
    ),
    (
        "What is the annual fee on the MBNA Rewards World Elite Mastercard's business variant?",
        "no_card_id:mbna-rewards-world-elite-business",
    ),
]


def build_unanswerable(cards_by_id: dict[str, Card]) -> list[dict[str, Any]]:
    results = []
    for question, tag in UNANSWERABLE_SPECS:
        kind, _, value = tag.partition(":")
        if kind == "no_card_id":
            assert value not in cards_by_id, f"{value} now exists -- question is answerable"
        results.append(
            {
                "question": question,
                "ground_truth": "Not found in the available card data or documents.",
                "relevant_card_ids": [],
                "answering_chunk_ids": [],
                "question_type": "unanswerable",
            }
        )
    return results


def load_cards() -> dict[str, Card]:
    raw = json.loads(CARDS_PATH.read_text(encoding="utf-8-sig"))
    return {c["card_id"]: Card.model_validate(c) for c in raw}


FULL_TARGETS = {
    "exact_term": 60,
    "paraphrase": 40,
    "exclusion": 40,
    "disambiguation": 30,
    "cross_source": 20,
    "unanswerable": 10,
}  # point 1i's approved category counts (200 total)
FULL_PATH = Path(__file__).resolve().parents[2] / "LLM" / "hard_questions_full.json"

# Paragraphs an external judge rejected (round 4, on a 40-question sample).
# Seeded into `claimed`, so no category drafts from them and the next-best
# candidate takes their place. Chunk ids only, no PDF text.
REJECTED_CHUNKS = {
    "nb-syncro-mc::cardholder_agreement::68": "twin (Amex SimplyCash Preferred) has same rule",
    "bmo-eclipse-vi::insurance_certificate::117": "twin (BMO Ascend) has the same pair-or-set rule",
    "amex-simplycash::cardholder_agreement::64": "asks for a definition it nearly repeats",
    "amex-simplycash-preferred::cardholder_agreement::64": "same definition-to-label question",
    "td-first-class-vi::cardholder_agreement::265": "asks for a label from its definition",
    "scotia-gold-amex::insurance_certificate::109": "fragment; never says which benefit it is for",
}

# The judge's own rewrites for questions worth keeping, applied after drafting
# so a rerun reproduces the same final set. Keyed by (question_type, chunk id).
# Made before any retrieval method has been run, so this is not tuning on scores.
JUDGE_FIXES = {
    ("disambiguation", "cibc-aeroplan-vi::insurance_certificate::165"): {
        "question": "Under the CIBC Aeroplan Visa Infinite Card certificate of insurance, does the "
        "cardholder's dependent child need to travel with the cardholder to be considered an "
        "insured person?"
    },
    ("disambiguation", "td-aeroplan-vi-privilege::cardholder_agreement::17"): {
        "question": "What must TD determine in its investigation before treating a transaction on "
        "my TD Aeroplan Visa Infinite Privilege Card as unauthorized?"
    },
    ("exact_term", "td-aeroplan-vi::cardholder_agreement::88"): {
        "question": "If I fail to call the administrator immediately or as soon as reasonably "
        "possible during a medical emergency, what is the reduced maximum benefit on my TD "
        "Aeroplan Visa Infinite Card?"
    },
    ("paraphrase", "td-aeroplan-vi::cardholder_agreement::194"): {
        "ground_truth": "Provided a loss-of-life benefit is payable, TD Life covers preparation "
        "and transportation of the insured person's body to their permanent city of residence, "
        "up to $10,000 per loss of life."
    },
    ("paraphrase", "rbc-westjet-mc::insurance_certificate::131"): {
        "question": "I paid $900 for my phone six months before it was stolen. With my WestJet "
        "RBC Mastercard claim approved, how much can I get back for an $800 replacement "
        "including taxes?",
        "ground_truth": "The maximum reimbursement is $712.80: the $900 phone loses 2% of its "
        "value per month over six months ($108.00), leaving a depreciated value of $792.00, "
        "less a deductible of $79.20.",
    },
    ("exclusion", "bmo-cashback-world-elite::insurance_certificate::175"): {
        "ground_truth": "The insured person's surviving parents are next in priority. If none "
        "survive, payment goes to surviving brothers and sisters, then to the estate if none "
        "of them survive."
    },
    ("cross_source", "bmo-eclipse-vi::cardholder_agreement::24"): {
        "ground_truth": "The annual fee is $120 CAD. Unauthorized-use liability is generally "
        "capped at $50 per transaction, with an exception for gross negligence or, in Quebec, "
        "gross fault in safeguarding the card, PIN, cheques or account information."
    },
}


def apply_judge_fixes(questions: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Returns the fixes that matched no question (their question wasn't
    drafted this run), so a silent miss is visible.
    """
    unused = []
    for (qtype, cid), patch in JUDGE_FIXES.items():
        matched = [
            q for q in questions if q["question_type"] == qtype and cid in q["answering_chunk_ids"]
        ]
        for q in matched:
            q.update(patch)
        if not matched:
            unused.append((qtype, cid))
    return unused


def validate_questions(
    questions: list[dict[str, Any]], targets: dict[str, int], known_ids: set[str]
) -> list[str]:
    """Problems that would quietly damage the eval set: a short category, a
    duplicate question, a paragraph backing two questions (it could then sit
    on both sides of the practice/final split), or a chunk id that isn't in
    the corpus. Empty list means clean.
    """
    problems = []
    counts: dict[str, int] = defaultdict(int)
    for q in questions:
        counts[q["question_type"]] += 1
    for category, target in targets.items():
        if counts[category] != target:
            problems.append(f"{category}: {counts[category]} of {target}")

    seen_questions: set[str] = set()
    seen_chunks: dict[str, str] = {}
    for q in questions:
        text = q["question"].strip().lower()
        if text in seen_questions:
            problems.append(f"duplicate question: {q['question'][:70]}")
        seen_questions.add(text)
        if not q.get("ground_truth"):
            problems.append(f"empty ground_truth: {q['question'][:70]}")
        for cid in q["answering_chunk_ids"]:
            if cid not in known_ids:
                problems.append(f"unknown chunk id: {cid}")
            # Fee chunks are per-card summaries; cross_source is limited to one
            # question per card, so they can't repeat either.
            if cid in seen_chunks:
                problems.append(f"chunk {cid} used by {seen_chunks[cid]} and {q['question_type']}")
            seen_chunks[cid] = q["question_type"]
    return problems


async def main() -> None:
    parser = argparse.ArgumentParser(description="Draft hard eval questions for review")
    parser.add_argument(
        "--per-category", type=int, default=4, help="How many to draft per category (default: 4)"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Draft the approved 200 (60/40/40/30/20/10) instead of --per-category",
    )
    parser.add_argument(
        "--max-paid-calls",
        type=int,
        default=None,
        help="Stop before making a paid Claude call past this many (cached calls are free)",
    )
    args = parser.parse_args()
    targets = FULL_TARGETS if args.full else dict.fromkeys(FULL_TARGETS, args.per_category)
    out_path = FULL_PATH if args.full else REVIEW_PATH
    generate_answer.max_paid_calls = args.max_paid_calls

    print(
        "Corpus cache: hit, no Pinecone read"
        if CORPUS_CACHE_PATH.exists()
        else "Corpus cache: miss, one Pinecone read (then saved)"
    )
    enable_disk_cache(CORPUS_CACHE_PATH)
    corpus = get_bm25_corpus()
    chunks = pdf_chunks(corpus)
    cards_by_id = load_cards()
    print(f"Loaded {len(chunks)} PDF chunks, {len(cards_by_id)} cards.", flush=True)

    # One at a time, in a fixed order, sharing `claimed`: which category gets
    # a paragraph both candidate lists want can then never depend on API
    # timing, so a rerun reproduces the same set. The costly-to-fill category
    # (disambiguation) goes last so a spending stop still leaves the rest done.
    claimed: set[str] = set(REJECTED_CHUNKS)
    by_category: dict[str, list[dict[str, Any]]] = {}
    stopped: str | None = None
    try:
        for category in ("exact_term", "paraphrase", "exclusion", "cross_source", "disambiguation"):
            n = targets[category]
            print(f"\n{category}: drafting {n}", flush=True)
            if category == "exact_term":
                by_category[category] = await build_exact_term(
                    chunks, n, claimed, by_category.setdefault(category, [])
                )
            elif category == "paraphrase":
                by_category[category] = await build_paraphrase(
                    chunks, n, claimed, by_category.setdefault(category, [])
                )
            elif category == "exclusion":
                by_category[category] = await build_exclusion(
                    chunks, n, claimed, by_category.setdefault(category, [])
                )
            elif category == "cross_source":
                by_category[category] = await build_cross_source(
                    chunks, cards_by_id, n, claimed, by_category.setdefault(category, [])
                )
            else:
                by_category[category] = await build_disambiguation(
                    chunks, n, claimed, by_category.setdefault(category, [])
                )
    except BudgetExceeded as stop:
        stopped = str(stop)
        print(f"\nSTOPPED EARLY: {stop}. Rerun to continue; paid calls are cached.", flush=True)
    by_category["unanswerable"] = build_unanswerable(cards_by_id)[: targets["unanswerable"]]

    all_questions = [q for items in by_category.values() for q in items]
    unused_fixes = apply_judge_fixes(all_questions)
    print(
        f"Judge fixes applied: {len(JUDGE_FIXES) - len(unused_fixes)} of {len(JUDGE_FIXES)}", end=""
    )
    print(f" (not in this set: {unused_fixes})" if unused_fixes else "")
    # Review-only enrichment: a human or an external LLM judging question
    # quality needs the actual source text to check grounding, not just a
    # chunk id. ground_truth.json stays id-only when this batch is merged
    # later -- carrying full chunk text into the frozen eval set would bloat
    # it for no reason once the source PDFs aren't in question anymore.
    text_by_id = {cid: meta.get("text", "") for cid, meta in zip(corpus.ids, corpus.metadatas)}
    for q in all_questions:
        q["eval_set"] = "hard"
        q["split"] = None  # assigned only once a full, approved batch is merged (not this script)
        q["source_chunks"] = [
            {"id": cid, "text": text_by_id.get(cid, "")} for cid in q["answering_chunk_ids"]
        ]
        if "distractor_chunk_id" in q:
            q["distractor_chunk_text"] = text_by_id.get(q["distractor_chunk_id"], "")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_questions, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {len(all_questions)} questions to {out_path}")
    for category, items in by_category.items():
        print(f"  {category}: {len(items)}/{targets[category]}")

    problems = validate_questions(all_questions, targets, set(corpus.ids))
    print("\nChecks:", "clean" if not problems else f"{len(problems)} problem(s)")
    for problem in problems:
        print(f"  - {problem}")

    print(
        f"\nClaude calls: {generate_answer.calls_made} paid, "
        f"{generate_answer.cache_hits} served from cache"
    )
    print("This is a review file, not the eval set -- ground_truth.json is untouched.")
    if stopped:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
