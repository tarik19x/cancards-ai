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
  uv run python ../tests/evals/run_coach_scenarios.py --replay          (what CI runs; free)
  uv run python ../tests/evals/run_coach_scenarios.py --export-replay   (re-record; paid)
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
# Committed, unlike the working cache above: the Claude replies CI plays back, and the floors
# the replayed results must stay above.
REPLAY_PATH = Path(__file__).parent / "coach_replay.json"
THRESHOLDS_PATH = Path(__file__).parent / "coach_thresholds.json"
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
                "reply": state.get("reply_markdown", ""),
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
    # The same question twice in a row means the user's answer did not move the
    # conversation on and the coach did not notice -- the loop found by using the chat.
    replies = [t["reply"] for t in turns if not t["gave_score"]]
    repeated = any(a == b for a, b in zip(replies, replies[1:], strict=False))
    return {
        "id": scenario["id"],
        "turns": turns,
        "repeated_question": repeated,
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
        "repeated_question_rate": sum(r["repeated_question"] for r in results) / n,
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


class RecordingGenerator(CachedGenerator):
    """Remembers which cache entries a run actually used, so a recording can be exported
    without the stale entries that earlier prompt versions left in the working cache."""

    def __init__(self, generate, path: Path):
        super().__init__(generate, path)
        self.used_keys: set[str] = set()

    async def __call__(self, system: str, user: str, max_tokens: int = 2000) -> str:
        self.used_keys.add(self._key(get_settings().llm_model, system, user, max_tokens))
        return await super().__call__(system, user, max_tokens)


class ReplayMiss(Exception):
    """A prompt was asked for that the recording does not contain."""


class ReplayGenerator:
    """Answers from the committed recording and can never reach the network."""

    def __init__(self, entries: dict[str, str], model: str):
        self._entries = entries
        self._model = model

    async def __call__(self, system: str, user: str, max_tokens: int = 2000) -> str:
        key = CachedGenerator._key(self._model, system, user, max_tokens)
        if key not in self._entries:
            raise ReplayMiss(
                "a prompt changed since the recording was made. Re-record it (real Claude "
                "calls, a few cents) with:\n"
                "  uv run python ../tests/evals/run_coach_scenarios.py --export-replay"
            )
        return self._entries[key]


def check_thresholds(gate_on: dict) -> list[str]:
    """Compare the gate-on results with the committed floors; empty means it passes."""
    limits = json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))
    summary = gate_on["summary"]
    failures = []
    for key, ceiling in limits["max"].items():
        if summary[key] > ceiling:
            failures.append(f"{key} is {summary[key]:.1%}, must be at most {ceiling:.0%}")
    for key, floor in limits["min"].items():
        value = summary[key]
        if value is None or value < floor:
            shown = "n/a" if value is None else (f"{value:.1%}" if value <= 1 else f"{value}")
            wanted = f"{floor:.0%}" if floor <= 1 else f"{floor}"
            failures.append(f"{key} is {shown}, must be at least {wanted}")
    return failures


async def main() -> None:
    parser = argparse.ArgumentParser(description="Measure the coach's readiness gate")
    parser.add_argument("--only", help="Run a single scenario by id")
    parser.add_argument(
        "--max-paid-calls",
        type=int,
        default=400,
        help="Stop before making more paid Claude calls than this (cached ones are free)",
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="CI mode: answer from the committed recording, no API keys or network, "
        "and exit 1 if the results fall below the committed thresholds",
    )
    parser.add_argument(
        "--export-replay",
        action="store_true",
        help="After a full run, write the Claude replies it used to the committed recording",
    )
    args = parser.parse_args()
    if args.replay and (args.only or args.export_replay):
        raise SystemExit("--replay runs the whole set and cannot be combined with other modes")

    scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    if args.only:
        scenarios = [s for s in scenarios if s["id"] == args.only]
        if not scenarios:
            raise SystemExit(f"no scenario with id {args.only!r}")

    if args.replay:
        recording = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
        # The recording is only valid for the model and year it was made with: both are
        # part of what the prompts (and so the lookup keys) contain.
        get_settings().llm_model = recording["model"]
        profile_module._current_year = lambda: recording["year"]  # noqa: SLF001
        generator = ReplayGenerator(recording["entries"], recording["model"])
        cached = None
    else:
        cached = RecordingGenerator(_uncached, CACHE_PATH)
        cached.max_paid_calls = args.max_paid_calls
        generator = cached
    profile_module.generate_answer = generator
    graph_module.generate_answer = generator

    print(f"{len(scenarios)} scenarios, each run with the gate off and on.")
    try:
        before = await run_config(scenarios, validation=False, label="before")
        after = await run_config(scenarios, validation=True, label="after")
    except BudgetExceeded as stop:
        # The cache writes itself after every paid call, so a stop here loses nothing.
        raise SystemExit(
            f"STOPPED EARLY: {stop}. Re-run to continue; paid calls are kept."
        ) from stop
    except ReplayMiss as miss:
        raise SystemExit(f"REPLAY FAILED: {miss}") from miss

    print(f"\n{'':<32}{'gate off':>12}{'gate on':>12}")
    for key in (
        "premature_advice_rate",
        "repeated_question_rate",
        "completion_rate",
        "field_extraction_accuracy",
        "score_exact_match_rate",
        "median_turns_to_score",
    ):
        b, a = before["summary"][key], after["summary"][key]
        fmt = lambda v: "-" if v is None else (f"{v:.0%}" if v <= 1 else f"{v:.1f}")  # noqa: E731
        print(f"{key:<32}{fmt(b):>12}{fmt(a):>12}")

    failures = [] if args.only else check_thresholds(after)
    if args.replay:
        # A CI run must not rewrite the committed results file.
        print("\nReplay only: coach_results.json left untouched.")
    else:
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

    if args.export_replay:
        if args.only:
            raise SystemExit("--export-replay needs the full set, not --only")
        recording = {
            "recorded_at": datetime.now(UTC).isoformat(),
            "model": get_settings().llm_model,
            "year": datetime.now(UTC).year,
            "entries": {k: cached._store[k] for k in sorted(cached.used_keys)},  # noqa: SLF001
        }
        REPLAY_PATH.write_text(json.dumps(recording, indent=1) + "\n", encoding="utf-8")
        print(f"Recording: {len(recording['entries'])} replies written to {REPLAY_PATH}")

    if failures:
        print("\nGATE FAILED:")
        for line in failures:
            print(f"  - {line}")
        raise SystemExit(1)
    print("\nGate passed: results are at or above the committed thresholds.")


if __name__ == "__main__":
    asyncio.run(main())
