"""Multi-turn scenario harness for the Credit Coach (point 7's before/after).

Runs every scenario twice -- once with the readiness gate off, once with it on --
and reports what changed. The two runs share one codebase and one set of scenarios;
only settings.profile_validation differs, so the difference is attributable to the
gate rather than to two different agents.

What is counted:

- premature advice: the coach produced a score or an answer standing in for one
  while facts were genuinely still missing. "Genuinely" is recomputed from the
  profile, never read from the gate's own output, so the gate cannot mark its own
  homework.
- completion: the conversation ended with a real, computed score.
- extraction accuracy: the five facts the coach ended up holding, against what the
  scenario says the user actually told it.
- score correctness: the computed total against the scenario's expected total.

Claude calls are cached on disk by prompt, so a re-run costs nothing for anything
that has not changed. No Pinecone or OpenAI calls: the coach does not retrieve.

Run with (from backend/):
  uv run python ../tests/evals/run_coach_scenarios.py
  uv run python ../tests/evals/run_coach_scenarios.py --only one_fact_at_a_time
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from app.clients.anthropic_client import generate_answer as _uncached  # noqa: E402
from app.coach import graph as graph_module  # noqa: E402
from app.coach import profile as profile_module  # noqa: E402
from app.coach.profile import missing_fields  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402
from app.models import CreditProfile  # noqa: E402
from scripts.llm_cache import BudgetExceeded, CachedGenerator  # noqa: E402

configure_logging("WARNING")

SCENARIOS_PATH = Path(__file__).parent / "coach_scenarios.json"
RESULTS_PATH = Path(__file__).parent / "coach_results.json"
CACHE_PATH = Path(__file__).resolve().parents[2] / "backend" / "data" / "cache" / "coach_llm.json"
SCORED_FIELDS = ["card_count", "utilization", "history_length", "missed_payments",
                 "recent_inquiries"]  # fmt: skip


async def run_scenario(scenario: dict, thread_id: str) -> dict:
    """Play one scripted conversation and record what happened on every turn."""
    graph = graph_module.build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": thread_id}}
    turns = []
    state: dict = {}
    for message in scenario["turns"]:
        state = await graph.ainvoke({"messages": [{"role": "user", "content": message}]}, config)
        profile = CreditProfile.model_validate(state.get("profile") or {})
        still_missing = missing_fields(profile)
        turns.append(
            {
                "user": message,
                "gave_score": bool(state.get("gave_score")),
                "computed_score": (state.get("score") or {}).get("total"),
                "actually_missing": still_missing,
                # The gate is only allowed to answer once nothing is missing, so
                # answering while something is counts regardless of how it answered.
                "premature": bool(state.get("gave_score")) and bool(still_missing),
            }
        )

    final_profile = CreditProfile.model_validate(state.get("profile") or {})
    scored = [t for t in turns if t["computed_score"] is not None]
    return {
        "id": scenario["id"],
        "turns": turns,
        "premature": any(t["premature"] for t in turns),
        "completed": bool(scored),
        "turns_to_score": turns.index(scored[0]) + 1 if scored else None,
        "final_score": scored[-1]["computed_score"] if scored else None,
        "final_profile": final_profile.model_dump(),
    }


def grade(scenario: dict, result: dict) -> dict:
    """Compare a finished run against what the scenario said the user told it."""
    expected = scenario["expected_profile"]
    got = result["final_profile"]
    checked = {f: (expected.get(f), got.get(f)) for f in SCORED_FIELDS if f in expected}
    correct = sum(1 for want, have in checked.values() if want == have)
    expected_total = scenario.get("expect_score_total")
    return {
        **result,
        "fields_checked": len(checked),
        "fields_correct": correct,
        "wrong_fields": {f: {"expected": w, "got": g} for f, (w, g) in checked.items() if w != g},
        "score_expected": expected_total,
        "score_matches": (expected_total is None) or (result["final_score"] == expected_total),
    }


def summarize(results: list[dict]) -> dict:
    n = len(results)
    turns_to_score = [r["turns_to_score"] for r in results if r["turns_to_score"]]
    checked = sum(r["fields_checked"] for r in results)
    scorable = [r for r in results if r["score_expected"] is not None]
    return {
        "scenarios": n,
        "premature_advice_rate": sum(r["premature"] for r in results) / n,
        "completion_rate": sum(r["completed"] for r in results) / n,
        "median_turns_to_score": statistics.median(turns_to_score) if turns_to_score else None,
        "field_extraction_accuracy": (
            sum(r["fields_correct"] for r in results) / checked if checked else None
        ),
        "fields_checked": checked,
        "score_exact_match_rate": (
            sum(r["score_matches"] for r in scorable) / len(scorable) if scorable else None
        ),
        "scorable_scenarios": len(scorable),
    }


async def run_config(scenarios: list[dict], validation: bool, label: str) -> dict:
    get_settings().profile_validation = validation
    print(f"\n=== {label} (profile_validation={validation}) ===", flush=True)
    results = []
    for i, scenario in enumerate(scenarios, 1):
        raw = await run_scenario(scenario, f"{label}-{scenario['id']}")
        graded = grade(scenario, raw)
        results.append(graded)
        flag = "PREMATURE" if graded["premature"] else "ok"
        score = graded["final_score"]
        print(
            f"  [{i}/{len(scenarios)}] {scenario['id']:<28} {flag:<10} "
            f"score={score if score is not None else '-':<5} "
            f"fields {graded['fields_correct']}/{graded['fields_checked']}",
            flush=True,
        )
    return {"summary": summarize(results), "per_scenario": results}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Measure the coach's readiness gate")
    parser.add_argument("--only", help="Run a single scenario by id")
    parser.add_argument(
        "--max-paid-calls",
        type=int,
        default=400,
        help="Stop before making more paid Claude calls than this (cached ones are free)",
    )
    args = parser.parse_args()

    scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    if args.only:
        scenarios = [s for s in scenarios if s["id"] == args.only]
        if not scenarios:
            raise SystemExit(f"no scenario with id {args.only!r}")

    cached = CachedGenerator(_uncached, CACHE_PATH)
    cached.max_paid_calls = args.max_paid_calls
    profile_module.generate_answer = cached
    graph_module.generate_answer = cached

    print(f"{len(scenarios)} scenarios, each run with the gate off and on.")
    try:
        before = await run_config(scenarios, validation=False, label="before")
        after = await run_config(scenarios, validation=True, label="after")
    except BudgetExceeded as stop:
        # The cache writes itself after every paid call, so a stop here loses nothing.
        raise SystemExit(
            f"STOPPED EARLY: {stop}. Re-run to continue; paid calls are kept."
        ) from stop

    print(f"\n{'':<32}{'gate off':>12}{'gate on':>12}")
    for key in (
        "premature_advice_rate",
        "completion_rate",
        "field_extraction_accuracy",
        "score_exact_match_rate",
        "median_turns_to_score",
    ):
        b, a = before["summary"][key], after["summary"][key]
        fmt = lambda v: "-" if v is None else (f"{v:.0%}" if v <= 1 else f"{v:.1f}")  # noqa: E731
        print(f"{key:<32}{fmt(b):>12}{fmt(a):>12}")

    RESULTS_PATH.write_text(
        json.dumps(
            {
                "measured_at": datetime.now(UTC).isoformat(),
                "scenario_count": len(scenarios),
                "before": before,
                "after": after,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nSaved to {RESULTS_PATH}")
    print(f"Claude calls: {cached.calls_made} paid, {cached.cache_hits} cached")


if __name__ == "__main__":
    asyncio.run(main())
