"""
Recall@k harness for CanCards AI retrieval.

Unlike run_evals.py, this has no LLM judge (RAGAS) in the loop -- it only
checks whether Pinecone returns the chunk IDs ground_truth.json labels as
correct -- so it has none of RAGAS's Windows/dill problems and can run
locally.

Each question is queried twice: once at top_k=8 for the reported recall@8,
once at top_k=50 for the recall@50 diagnostic. These can't be collapsed into
one top_k=50 query sliced down to 8 -- that shortcut only holds for a single
globally-ranked list (true for dense-only Pinecone search, where the top_k
cutoff doesn't change relative order). It breaks for hybrid mode: RRF fuses
whatever candidate pool it's given, so fusing at depth 50 and slicing to 8
produces a different ranking than actually fusing at depth 8 -- a real bug
this harness had until it was caught by a hybrid run that looked far worse
than dense-only for no principled reason. Per point 1's k=8 decision,
recall@8 is what gets reported, since 8 is what the LLM actually reads.

Usage (from backend/, matching run_evals.py's invocation convention):
  uv run python ../tests/evals/measure_recall.py --save-as dense_only
  uv run python ../tests/evals/measure_recall.py --eval-set hard --split practice \
    --save-as hard_dense

The hard set is frozen (hard_set_lock.json). Its final split is meant to be run
once per method, so --split final also needs --confirm-final.
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.logging_config import configure_logging  # noqa: E402
from app.rag.retrieve import retrieve_chunks  # noqa: E402

configure_logging("WARNING")

GROUND_TRUTH_PATH = Path(__file__).parent / "ground_truth.json"
RESULTS_PATH = Path(__file__).parent / "recall_results.json"
DIAGNOSTIC_K = 50
REPORTED_K = 8


def select_questions(
    questions: list[dict], eval_set: str, split: str | None
) -> tuple[list[dict], int]:
    """Returns (questions to run, how many unanswerable ones were skipped).

    "legacy" is everything that predates the hard set (the 60 easy and 11 pilot
    questions), so a bare run behaves exactly as it always did.
    """
    if eval_set == "legacy":
        chosen = [q for q in questions if q.get("eval_set") != "hard"]
    else:
        chosen = [q for q in questions if q.get("eval_set") == "hard" and q.get("split") == split]
    answerable = [q for q in chosen if q["answering_chunk_ids"]]
    return answerable, len(chosen) - len(answerable)


def recall_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    """Fraction of relevant_ids found in the first k retrieved_ids."""
    top_k = set(retrieved_ids[:k])
    hits = sum(1 for rid in relevant_ids if rid in top_k)
    return hits / len(relevant_ids)


async def run_one(item: dict, mode: str) -> dict:
    reported_matches = await retrieve_chunks(item["question"], top_k=REPORTED_K, mode=mode)
    diagnostic_matches = await retrieve_chunks(item["question"], top_k=DIAGNOSTIC_K, mode=mode)
    relevant_ids = item["answering_chunk_ids"]
    return {
        "question": item["question"],
        "question_type": item["question_type"],
        "relevant_chunk_ids": relevant_ids,
        f"recall_at_{REPORTED_K}": recall_at_k(
            [m["id"] for m in reported_matches], relevant_ids, REPORTED_K
        ),
        f"recall_at_{DIAGNOSTIC_K}": recall_at_k(
            [m["id"] for m in diagnostic_matches], relevant_ids, DIAGNOSTIC_K
        ),
    }


def summarize(results: list[dict]) -> dict:
    def macro_avg(field: str, subset: list[dict]) -> float:
        return sum(r[field] for r in subset) / len(subset) if subset else 0.0

    reported_field = f"recall_at_{REPORTED_K}"
    diagnostic_field = f"recall_at_{DIAGNOSTIC_K}"
    by_type: dict[str, list[dict]] = {}
    for r in results:
        by_type.setdefault(r["question_type"], []).append(r)

    return {
        "question_count": len(results),
        reported_field: macro_avg(reported_field, results),
        f"{diagnostic_field}_diagnostic_only": macro_avg(diagnostic_field, results),
        "by_question_type": {
            qtype: {
                "count": len(subset),
                reported_field: macro_avg(reported_field, subset),
            }
            for qtype, subset in by_type.items()
        },
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Measure recall@k against ground_truth.json")
    parser.add_argument(
        "--save-as",
        help="Label for this run in recall_results.json (e.g. dense_only, hybrid, reranked)",
        default="dense_only",
    )
    parser.add_argument(
        "--mode",
        choices=["dense", "hybrid"],
        default="dense",
        help="retrieve_chunks mode to measure (default: dense, matching retrieve_chunks' default)",
    )
    parser.add_argument(
        "--eval-set",
        choices=["legacy", "hard"],
        default="legacy",
        help="legacy = the 60 easy + 11 pilot questions (default); hard = the frozen 200",
    )
    parser.add_argument("--split", choices=["practice", "final"], help="Needed for --eval-set hard")
    parser.add_argument(
        "--confirm-final",
        action="store_true",
        help="Required for --split final: the final 100 is run once per method",
    )
    args = parser.parse_args()
    if args.eval_set == "hard" and not args.split:
        parser.error("--eval-set hard needs --split practice or --split final")
    if args.split == "final" and not args.confirm_final:
        parser.error("--split final needs --confirm-final (the final set is run once per method)")
    if args.eval_set == "legacy" and args.split:
        parser.error("--split only applies to --eval-set hard")

    questions, skipped = select_questions(
        json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8")), args.eval_set, args.split
    )
    if skipped:
        print(f"Skipped {skipped} unanswerable questions (no chunk to find).")
    print(
        f"Loaded {len(questions)} questions. mode={args.mode}, "
        f"querying top_k={REPORTED_K} and top_k={DIAGNOSTIC_K}..."
    )

    results = []
    for i, item in enumerate(questions, 1):
        result = await run_one(item, args.mode)
        results.append(result)
        recall = result[f"recall_at_{REPORTED_K}"]
        print(f"  [{i}/{len(questions)}] recall@{REPORTED_K}={recall:.2f}  {item['question'][:60]}")

    summary = summarize(results)
    print(f"\n{'=' * 50}")
    print(f"  recall@{REPORTED_K} (reported): {summary[f'recall_at_{REPORTED_K}']:.4f}")
    print(
        f"  recall@{DIAGNOSTIC_K} (diagnostic only): "
        f"{summary[f'recall_at_{DIAGNOSTIC_K}_diagnostic_only']:.4f}"
    )
    for qtype, stats in summary["by_question_type"].items():
        print(
            f"    {qtype} (n={stats['count']}): recall@{REPORTED_K}="
            f"{stats[f'recall_at_{REPORTED_K}']:.4f}"
        )
    print(f"{'=' * 50}\n")

    all_runs: dict = {}
    if RESULTS_PATH.exists():
        all_runs = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    all_runs[args.save_as] = {
        "summary": summary,
        "per_question": results,
        "measured_at": datetime.now(UTC).isoformat(),
    }
    RESULTS_PATH.write_text(json.dumps(all_runs, indent=2) + "\n", encoding="utf-8")
    print(f"Saved under key '{args.save_as}' in {RESULTS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
