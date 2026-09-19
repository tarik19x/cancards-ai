"""Merge the approved hard eval questions into tests/evals/ground_truth.json,
split them 100 practice / 100 final, and write the freeze lock (point 1j-iii).

Dry run by default: prints the plan and touches nothing. Pass --write to merge.

The split is stratified (each category is halved) and decided by a hash of the
question text, never by how any retrieval method scores a question. Questions
whose twin paragraph is another question's answer stay on the same side, so a
method tuned on the practice set cannot see the twin of a final question.

The lock (tests/evals/hard_set_lock.json) fingerprints the fields retrieval
measurement depends on: the question, its labelled chunks, its type and its
split. ground_truth wording is deliberately outside it, so answer text can
still be corrected for the answer-quality evals without unfreezing recall.

Run with (from backend/):
  uv run python -m scripts.merge_hard_eval_questions            # dry run
  uv run python -m scripts.merge_hard_eval_questions --write
"""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.generate_hard_eval_questions import FULL_PATH, FULL_TARGETS, _stable_rank

EVALS_DIR = Path(__file__).resolve().parents[2] / "tests" / "evals"
GROUND_TRUTH_PATH = EVALS_DIR / "ground_truth.json"
LOCK_PATH = EVALS_DIR / "hard_set_lock.json"

LOCKED_FIELDS = ("question", "answering_chunk_ids", "relevant_card_ids", "question_type", "split")


def to_entry(q: dict[str, Any]) -> dict[str, Any]:
    """Id-only record: chunk text stays out of the repo (the PDFs are not committed)."""
    entry = {
        "question": q["question"],
        "ground_truth": q["ground_truth"],
        "relevant_card_ids": q["relevant_card_ids"],
        "answering_chunk_ids": q["answering_chunk_ids"],
        "question_type": q["question_type"],
        "eval_set": "hard",
        "split": q["split"],
    }
    if "distractor_chunk_id" in q:
        entry["distractor_chunk_id"] = q["distractor_chunk_id"]  # the trap; not a right answer
    return entry


def _components(questions: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Groups of questions tied together by a twin: one question's distractor
    paragraph is another question's answer paragraph."""
    by_chunk = {cid: q for q in questions for cid in q["answering_chunk_ids"]}
    parent = list(range(len(questions)))
    index = {id(q): i for i, q in enumerate(questions)}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for q in questions:
        other = by_chunk.get(q.get("distractor_chunk_id", ""))
        if other is not None and other is not q:
            parent[find(index[id(q)])] = find(index[id(other)])
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for q in questions:
        groups[find(index[id(q)])].append(q)
    return list(groups.values())


def assign_splits(questions: list[dict[str, Any]]) -> None:
    """Sets q["split"] to "practice" or "final", halving every category."""
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for q in questions:
        by_category[q["question_type"]].append(q)

    for category, items in by_category.items():
        assert len(items) % 2 == 0, f"{category} has an odd count ({len(items)}); cannot halve"
        half = len(items) // 2
        groups = _components(items)
        for group in groups:
            assert all(q["question_type"] == category for q in group)
        key = lambda group: min(_stable_rank("split:" + q["question"]) for q in group)  # noqa: E731
        linked = sorted((g for g in groups if len(g) > 1), key=key)
        single = sorted((g for g in groups if len(g) == 1), key=key)

        counts = {"practice": 0, "final": 0}
        for group in linked:  # place the ties first, on whichever side has fewer
            side = "practice" if counts["practice"] <= counts["final"] else "final"
            counts[side] += len(group)
            for q in group:
                q["split"] = side
        for group in single:
            side = "practice" if counts["practice"] < half else "final"
            counts[side] += 1
            group[0]["split"] = side
        assert counts["practice"] == counts["final"] == half, f"{category}: {counts}"


def fingerprint(entries: list[dict[str, Any]]) -> str:
    """Hash of the retrieval-relevant fields of every hard question."""
    hard = [e for e in entries if e.get("eval_set") == "hard"]
    projected = sorted(
        ({field: e[field] for field in LOCKED_FIELDS} for e in hard), key=lambda e: e["question"]
    )
    blob = json.dumps(projected, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def tag_existing(entries: list[dict[str, Any]]) -> None:
    """The 60 card-data questions are the easy slice; the 11 PDF questions are the pilot (1i)."""
    for e in entries:
        if "eval_set" not in e:
            e["eval_set"] = "pilot" if e["question_type"] == "pdf_grounded" else "easy"


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge, split and freeze the hard eval set")
    parser.add_argument("--write", action="store_true", help="Actually merge (default: dry run)")
    args = parser.parse_args()

    existing = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    if any(e.get("eval_set") == "hard" for e in existing):
        raise SystemExit("ground_truth.json already holds the hard set; it is frozen. Stopping.")
    drafted = json.loads(FULL_PATH.read_text(encoding="utf-8"))

    counts = Counter(q["question_type"] for q in drafted)
    assert dict(counts) == FULL_TARGETS, f"category counts {dict(counts)} != {FULL_TARGETS}"
    assign_splits(drafted)

    merged = existing + [to_entry(q) for q in drafted]
    tag_existing(merged)

    kept = Counter(e["eval_set"] for e in merged if e["eval_set"] != "hard")
    print(f"Existing questions kept: {len(existing)} ({dict(kept)})")
    print("Hard questions by category and split:")
    for category in FULL_TARGETS:
        row = Counter(q["split"] for q in drafted if q["question_type"] == category)
        print(f"  {category:<15} practice={row['practice']:>3} final={row['final']:>3}")
    total = Counter(q["split"] for q in drafted)
    print(f"  {'TOTAL':<15} practice={total['practice']:>3} final={total['final']:>3}")
    print(f"Fingerprint: {fingerprint(merged)}")

    if not args.write:
        print("\nDry run: nothing written. Re-run with --write to merge and freeze.")
        return

    GROUND_TRUTH_PATH.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    lock = {
        "frozen_at": datetime.now(UTC).isoformat(),
        "fingerprint": fingerprint(merged),
        "locked_fields": list(LOCKED_FIELDS),
        "counts": {
            "practice": total["practice"],
            "final": total["final"],
        },
        "note": "Never edit, add or drop a hard question because of how a method scored it.",
    }
    LOCK_PATH.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {len(merged)} questions to {GROUND_TRUTH_PATH}\nWrote lock to {LOCK_PATH}")


if __name__ == "__main__":
    main()
