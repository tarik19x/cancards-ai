"""
RAGAS evaluation runner for CanCards AI.

Usage:
  python tests/evals/run_evals.py --save-baseline
  python tests/evals/run_evals.py --limit 5
  python tests/evals/run_evals.py
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.logging_config import configure_logging, get_logger
from app.rag.generate import generate_response
from app.rag.retrieve import retrieve_chunks

configure_logging("WARNING")
log = get_logger(__name__)

GROUND_TRUTH_PATH = Path(__file__).parent / "ground_truth.json"
BASELINE_PATH = Path(__file__).parent / "baseline.json"
REGRESSION_THRESHOLD = 0.05


async def run_single(question: str) -> dict:
    chunks = await retrieve_chunks(question, top_k=12)
    if not chunks:
        return {"question": question, "answer": "No relevant information found.", "contexts": []}
    response = await generate_response(question, chunks)
    return {
        "question": question,
        "answer": response.answer_markdown,
        "contexts": [c["metadata"]["text"] for c in chunks],
    }


async def run_eval(questions: list, limit: int | None = None) -> list:
    subset = questions[:limit] if limit else questions
    print(f"\nRunning eval on {len(subset)} questions...")
    results = []
    for i, item in enumerate(subset, 1):
        print(f"  [{i}/{len(subset)}] {item['question'][:60]}...")
        result = await run_single(item["question"])
        result["ground_truth"] = item["ground_truth"]
        results.append(result)
    return results


def compute_ragas_scores(results: list) -> dict:
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics.collections import Faithfulness, ContextPrecision
        from openai import OpenAI
        from ragas.llms import llm_factory
    except ImportError:
        print("ERROR: RAGAS not installed. Run: uv add --dev ragas datasets")
        sys.exit(1)

    llm = llm_factory("gpt-4o-mini", client=OpenAI())

    faithfulness_metric = Faithfulness(llm=llm)
    context_precision_metric = ContextPrecision(llm=llm)

    dataset = Dataset.from_list(results)
    scores = evaluate(
        dataset=dataset,
        metrics=[faithfulness_metric, context_precision_metric],
    )

    def safe_float(val: object) -> float:
        if isinstance(val, list):
            valid = [v for v in val if v is not None]
            return float(sum(valid) / len(valid)) if valid else 0.0
        return float(val) if val is not None else 0.0

    return {
        "faithfulness": safe_float(scores["faithfulness"]),
        "context_precision": safe_float(scores["context_precision"]),
        "question_count": len(results),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def check_regression(current: dict, baseline: dict) -> list:
    regressions = []
    for metric in ["faithfulness", "context_precision"]:
        drop = baseline.get(metric, 0) - current.get(metric, 0)
        if drop > REGRESSION_THRESHOLD:
            regressions.append(
                f"  REGRESSION: {metric} dropped {drop:.3f} "
                f"(baseline: {baseline.get(metric, 0):.3f}, "
                f"current: {current.get(metric, 0):.3f})"
            )
    return regressions


def print_scores(scores: dict, label: str = "Scores") -> None:
    print(f"\n{'='*50}")
    print(f"  {label}")
    print(f"{'='*50}")
    print(f"  Faithfulness:        {scores['faithfulness']:.3f}")
    print(f"  Context Precision:   {scores['context_precision']:.3f}")
    print(f"  Questions evaluated: {scores['question_count']}")
    print(f"{'='*50}\n")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run RAGAS evals for CanCards AI")
    parser.add_argument("--save-baseline", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(ground_truth)} ground truth questions")

    results = await run_eval(ground_truth, limit=args.limit)

    print("\nComputing RAGAS metrics (this calls OpenAI)...")
    scores = compute_ragas_scores(results)
    print_scores(scores, label="Current Scores")

    if args.save_baseline:
        BASELINE_PATH.write_text(json.dumps(scores, indent=2), encoding="utf-8")
        print(f"Baseline saved to {BASELINE_PATH}")
        return

    if not BASELINE_PATH.exists():
        print("No baseline found. Saving current scores as baseline...")
        BASELINE_PATH.write_text(json.dumps(scores, indent=2), encoding="utf-8")
        return

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    print_scores(baseline, label="Baseline Scores")

    regressions = check_regression(scores, baseline)
    if regressions:
        print("FAIL - Quality regression detected:")
        for msg in regressions:
            print(msg)
        sys.exit(1)
    else:
        print("PASS - No regressions detected.")


if __name__ == "__main__":
    asyncio.run(main())