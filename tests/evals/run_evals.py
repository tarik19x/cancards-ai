"""
RAGAS evaluation runner for CanCards AI.

Evaluates the streaming path — the same prompt, sentinel contract and parser that
/api/ask/stream serves. Scoring the non-streaming path instead would leave the
prompt users actually hit ungraded.

IMPORTANT: This script runs in CI (GitHub Actions on Ubuntu) only.
Do NOT run locally on Windows — RAGAS has an unfixable Windows bug in the dill package.

Usage in CI (triggered via GitHub Actions):
  --save-baseline  Save current scores as the new baseline
  --limit N        Only run N questions (faster for testing)
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add backend/ to sys.path so we can import app modules
# __file__ = tests/evals/run_evals.py
# parents[2] = repo root (cancards-ai/)
# parents[2] / "backend" = cancards-ai/backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.logging_config import configure_logging, get_logger  # noqa: E402
from app.rag.retrieve import retrieve_chunks  # noqa: E402
from app.rag.stream import stream_rag_response  # noqa: E402

configure_logging("WARNING")
log = get_logger(__name__)

GROUND_TRUTH_PATH = Path(__file__).parent / "ground_truth.json"
BASELINE_PATH = Path(__file__).parent / "baseline.json"
REGRESSION_THRESHOLD = 0.05
TOP_K = 12


async def answer_via_stream(question: str, chunks: list) -> str:
    """Consume the SSE generator and return the final answer_markdown.

    Reads the done event rather than concatenating tokens — the token stream stops
    at the CARDS sentinel, so only the done event carries the settled answer.
    """
    async for raw in stream_rag_response(question, chunks):
        payload = json.loads(raw.removeprefix("data: ").strip())
        if payload["type"] == "done":
            return payload["response"]["answer_markdown"]
        if payload["type"] == "error":
            raise RuntimeError(f"stream failed: {payload['message']}")
    raise RuntimeError("stream ended without a done event")


async def run_single(question: str) -> dict:
    chunks = await retrieve_chunks(question, top_k=TOP_K)
    if not chunks:
        return {
            "question": question,
            "answer": "No relevant information found.",
            "contexts": [],
            "ground_truth": "",
        }
    answer = await answer_via_stream(question, chunks)
    return {
        "question": question,
        "answer": answer,
        "contexts": [c["metadata"]["text"] for c in chunks],
        "ground_truth": "",  # filled in by run_eval
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
    """
    Uses ragas 0.4.x API.

    Key points:
    - EvaluationDataset + SingleTurnSample (not HuggingFace Dataset)
    - Faithfulness() and ContextPrecision() instantiated with NO arguments
    - ragas 0.4.x auto-configures LLM from OPENAI_API_KEY environment variable
    - llm_factory removed — incompatible with 0.4.x metric constructors
    - answer_relevancy removed — causes embed_query timeout
    - Import from ragas.metrics directly (not ragas.metrics.collections)

    The judge model is whatever ragas defaults to, so the version is recorded
    alongside the scores — a default change would otherwise move the baseline
    with nothing in the diff to show why.
    """
    try:
        import ragas
        from ragas import EvaluationDataset, SingleTurnSample, evaluate
        from ragas.metrics import ContextPrecision, Faithfulness
    except ImportError as e:
        print(f"ERROR: Missing dependency: {e}")
        print("Make sure ragas is in pyproject.toml dev dependencies and uv.lock is up to date.")
        sys.exit(1)

    # Instantiate with no arguments — ragas 0.4.x auto-configures
    # LLM from OPENAI_API_KEY environment variable set in evals.yml
    faithfulness_metric = Faithfulness()
    context_precision_metric = ContextPrecision()

    # Build ragas 0.4.x dataset — Dataset.from_list() no longer accepted
    samples = [
        SingleTurnSample(
            user_input=r["question"],
            response=r["answer"],
            retrieved_contexts=r["contexts"],
            reference=r["ground_truth"],
        )
        for r in results
    ]
    eval_dataset = EvaluationDataset(samples=samples)

    scores = evaluate(
        dataset=eval_dataset,
        metrics=[faithfulness_metric, context_precision_metric],
    )

    def safe_float(val: object) -> float:
        """Handle both float and list return types from ragas."""
        if isinstance(val, list):
            valid = [v for v in val if v is not None]
            return float(sum(valid) / len(valid)) if valid else 0.0
        return float(val) if val is not None else 0.0

    return {
        "faithfulness": safe_float(scores["faithfulness"]),
        "context_precision": safe_float(scores["context_precision"]),
        "question_count": len(results),
        "evaluated_path": "stream",
        "ragas_version": ragas.__version__,
        "evaluated_at": datetime.now(UTC).isoformat(),
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
    print(f"\n{'=' * 50}")
    print(f"  {label}")
    print(f"{'=' * 50}")
    print(f"  Faithfulness:        {scores['faithfulness']:.3f}")
    print(f"  Context Precision:   {scores['context_precision']:.3f}")
    print(f"  Questions evaluated: {scores['question_count']}")
    print(f"  Path evaluated:      {scores.get('evaluated_path', 'unknown')}")
    print(f"{'=' * 50}\n")


def save_baseline(scores: dict) -> None:
    """Write the baseline and tell the caller it still has to be committed.

    The workflow runs on an ephemeral checkout, so writing the file is only half
    the job — without the upload step the new baseline dies with the runner.
    """
    BASELINE_PATH.write_text(json.dumps(scores, indent=2) + "\n", encoding="utf-8")
    print(f"Baseline written to {BASELINE_PATH}")
    print("This file must be committed to take effect — download it from the")
    print("workflow's 'ragas-baseline' artifact and commit it to the repo.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run RAGAS evals for CanCards AI")
    parser.add_argument(
        "--save-baseline", action="store_true", help="Save current scores as the baseline"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit number of questions (faster for testing)"
    )
    args = parser.parse_args()

    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(ground_truth)} ground truth questions")

    results = await run_eval(ground_truth, limit=args.limit)

    print("\nComputing RAGAS metrics (this calls OpenAI)...")
    scores = compute_ragas_scores(results)
    print_scores(scores, label="Current Scores")

    if args.save_baseline:
        save_baseline(scores)
        return

    # A missing or placeholder baseline used to self-certify whatever this run
    # scored. Fail instead — an unguarded run should never report green.
    if not BASELINE_PATH.exists():
        print("FAIL - No baseline to compare against.")
        print("  Re-run this workflow with save_baseline=yes, then commit the result.")
        sys.exit(1)

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if baseline.get("question_count", 0) == 0:
        print("FAIL - Baseline is a placeholder (question_count is 0).")
        print("  Re-run this workflow with save_baseline=yes, then commit the result.")
        sys.exit(1)

    if baseline.get("evaluated_path") != scores["evaluated_path"]:
        print(
            f"WARNING: baseline was measured on the "
            f"'{baseline.get('evaluated_path', 'unknown')}' path, "
            f"this run used '{scores['evaluated_path']}'. Scores are not comparable — "
            f"re-baseline before trusting the gate."
        )

    print_scores(baseline, label="Baseline Scores")

    regressions = check_regression(scores, baseline)
    if regressions:
        print("FAIL - Quality regression detected:")
        for msg in regressions:
            print(msg)
        print("\nTo update the baseline if this regression is acceptable:")
        print("  Trigger the eval workflow with save_baseline=yes, then commit the artifact.")
        sys.exit(1)
    else:
        print("PASS - No regressions detected.")


if __name__ == "__main__":
    asyncio.run(main())
