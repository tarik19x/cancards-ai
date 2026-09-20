"""Latency of the Credit Coach under concurrent users, against the real model and database.

Each simulated user holds one conversation and sends its turns back to back with no thinking
time: the five questions, the turn that produces the score, then one follow-up. That is harsher
than people typing, which spreads real requests out.

What is reported: per-request latency (client side, includes the model calls and the Postgres
checkpoint), its median / 95th / 99th percentile, the share under a target, and errors. Turns
are split by kind because they do different work:
  question  extract facts (one model call) and reply with a fixed question
  score     extract + score + explain (two model calls)
  follow-up extract + answer from the saved facts (two model calls)

The API runs as a separate process from serve_unlimited.py (same code, real Neon, rate limit off,
no Pinecone). Client and server share this machine, so the result is a local figure, not the
deployed Lightsail container's: say so when quoting it.

  uv run python ../tests/evals/loadtest_coach.py                      15 users, 3.8 s target
  uv run python ../tests/evals/loadtest_coach.py --users 5 --target 3.8
"""

import argparse
import asyncio
import json
import math
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

RESULTS_PATH = HERE / "loadtest_results.json"
SERVER_LOG = BACKEND / "data" / "cache" / "loadtest_server.log"  # gitignored folder
MACHINE_NOTE = "client and server on one Windows laptop; real Neon and Claude; rate limit off"

TURNS = [
    ("question", "Hi, I'd like to check my credit health."),
    ("question", "3 cards"),
    ("question", "I usually owe about $4000 on a $10000 limit"),
    ("question", "since 2019"),
    ("question", "never late"),
    ("score", "none"),
    ("follow-up", "How can I improve it fastest?"),
]


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    # Nearest-rank: the smallest value at or above pct% of the samples.
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


async def one_user(client: httpx.AsyncClient, user: int, threads: list[str]) -> list[dict]:
    rows: list[dict] = []
    thread_id: str | None = None
    for kind, message in TURNS:
        body = {"message": message, **({"thread_id": thread_id} if thread_id else {})}
        started = time.perf_counter()
        try:
            response = await client.post("/api/coach/chat", json=body)
            elapsed = time.perf_counter() - started
            ok = response.status_code == 200
            if ok:
                data = response.json()
                thread_id = data["thread_id"]
                if thread_id not in threads:
                    threads.append(thread_id)
                # A reply of the wrong kind means the conversation did not go as scripted.
                if kind == "score" and not data.get("gave_score"):
                    ok = False
            rows.append({"user": user, "kind": kind, "seconds": elapsed, "ok": ok,
                         "status": response.status_code})  # fmt: skip
        except httpx.HTTPError as exc:
            rows.append({"user": user, "kind": kind, "seconds": time.perf_counter() - started,
                         "ok": False, "status": type(exc).__name__})  # fmt: skip
            break  # a user whose conversation broke stops, like a real one would
    return rows


def summarize(rows: list[dict], target: float) -> dict:
    good = [r["seconds"] for r in rows if r["ok"]]
    out = {
        "requests": len(rows),
        "errors": sum(not r["ok"] for r in rows),
        "under_target": (sum(s <= target for s in good) / len(rows)) if rows else 0.0,
    }
    if good:
        out |= {"median": percentile(good, 50), "p95": percentile(good, 95),
                "p99": percentile(good, 99), "max": max(good)}  # fmt: skip
    return out


async def run_load(base_url: str, users: int, target: float, threads: list[str]) -> dict:
    limits = httpx.Limits(max_connections=users + 5)
    async with httpx.AsyncClient(base_url=base_url, timeout=120, limits=limits) as client:
        started = time.perf_counter()
        per_user = await asyncio.gather(*(one_user(client, i, threads) for i in range(users)))
        wall = time.perf_counter() - started
    rows = [row for user_rows in per_user for row in user_rows]
    by_kind = {
        kind: summarize([r for r in rows if r["kind"] == kind], target)
        for kind in ("question", "score", "follow-up")
    }
    statuses = sorted({str(r["status"]) for r in rows if not r["ok"]})
    return {"users": users, "wall_seconds": wall, "overall": summarize(rows, target),
            "by_kind": by_kind, "error_statuses": statuses}  # fmt: skip


def start_server(port: int, memory_only: bool, fake_delay: float | None = None) -> subprocess.Popen:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if fake_delay is not None:
        env["FAKE_MODEL_DELAY"] = str(fake_delay)  # stub model: measures the app, not Claude
    if memory_only:
        env["DATABASE_URL"] = ""  # an empty value beats .env: conversations stay in memory
    # To a file, never a pipe nobody reads: the app logs every turn, and once a pipe's buffer
    # fills the server blocks on its own logging and every request after it hangs.
    SERVER_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_file = SERVER_LOG.open("wb")
    proc = subprocess.Popen(
        [sys.executable, str(HERE / "serve_unlimited.py"), "--port", str(port)],
        cwd=BACKEND, env=env, stdout=log_file, stderr=subprocess.STDOUT,
    )  # fmt: skip
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=2).status_code == 200:
                return proc
        except httpx.HTTPError:
            pass
        if proc.poll() is not None:
            tail = SERVER_LOG.read_text(encoding="utf-8", errors="replace")[-400:]
            raise SystemExit("the test server exited: " + tail)
        time.sleep(0.5)
    proc.kill()
    raise SystemExit("the test server did not become healthy in 60 seconds")


def delete_threads(threads: list[str]) -> None:
    """Remove the test conversations from Neon so the load test leaves nothing behind."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    from app.config import get_settings

    url = get_settings().database_url
    if not url or not threads:
        return

    async def go() -> None:
        async with AsyncPostgresSaver.from_conn_string(url) as saver:
            for thread_id in threads:
                await saver.adelete_thread(thread_id)

    asyncio.run(go(), loop_factory=asyncio.SelectorEventLoop)


def show(label: str, result: dict, target: float) -> None:
    o = result["overall"]
    print(f"\n{label}: {result['users']} user(s), {o['requests']} requests in "
          f"{result['wall_seconds']:.1f}s, errors {o['errors']}")  # fmt: skip
    if "median" in o:
        print(f"  overall   median {o['median']:.2f}s  p95 {o['p95']:.2f}s  p99 {o['p99']:.2f}s  "
              f"max {o['max']:.2f}s  under {target}s: {o['under_target']:.0%}")  # fmt: skip
    for kind, k in result["by_kind"].items():
        if "median" in k:
            print(f"  {kind:<10}median {k['median']:.2f}s  p95 {k['p95']:.2f}s  "
                  f"max {k['max']:.2f}s  under {target}s: {k['under_target']:.0%}  "
                  f"(n={k['requests']})")  # fmt: skip
    if result["error_statuses"]:
        print("  error statuses:", ", ".join(result["error_statuses"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Load test the Credit Coach")
    parser.add_argument("--users", type=int, default=15)
    parser.add_argument("--target", type=float, default=3.8, help="seconds")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument(
        "--memory", action="store_true", help="diagnostic: keep conversations in memory, no Neon"
    )
    parser.add_argument(
        "--fake-model-delay",
        type=float,
        default=None,
        metavar="SECONDS",
        help="diagnostic: stub the model (it answers after SECONDS) to measure the app alone; free",
    )
    parser.add_argument("--keep-threads", action="store_true", help="do not delete test chats")
    args = parser.parse_args()

    threads: list[str] = []
    server = start_server(args.port, args.memory, args.fake_model_delay)
    base = f"http://127.0.0.1:{args.port}"
    try:
        # One warm-up conversation first: the first request pays for connection setup and cold
        # imports, which is real but not what "concurrent users" measures.
        asyncio.run(run_load(base, 1, args.target, threads))
        alone = asyncio.run(run_load(base, 1, args.target, threads))
        if alone["overall"]["errors"]:
            # A broken baseline (no API credit, a bad deploy) would turn 15 users into 100+
            # failed requests, each leaving an empty conversation behind in the database.
            raise SystemExit(
                f"the 1-user baseline already failed ({', '.join(alone['error_statuses'])}); "
                f"not starting the concurrent run. Server log: {SERVER_LOG}"
            )
        loaded = asyncio.run(run_load(base, args.users, args.target, threads))
        try:
            spent = httpx.get(f"{base}/_usage", timeout=5).json()
            print(
                f"Claude usage for this whole run: {spent['calls']} calls, about "
                f"${spent['cost_usd']:.2f} (cache read {spent['cache_read_tokens']:,} tokens)"
            )
        except httpx.HTTPError:
            pass
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        if not args.keep_threads:
            delete_threads(threads)

    show("1 user (baseline)", alone, args.target)
    show(f"{args.users} users at once", loaded, args.target)
    out_path = RESULTS_PATH
    if args.memory:
        out_path = RESULTS_PATH.with_name("loadtest_results_memory.json")
    if args.fake_model_delay is not None:
        out_path = RESULTS_PATH.with_name("loadtest_results_stub_model.json")
    out_path.write_text(
        json.dumps({"measured_at": datetime.now(UTC).isoformat(), "target_seconds": args.target,
                    "machine_note": MACHINE_NOTE,
                    "baseline": alone, "loaded": loaded}, indent=2) + "\n",
        encoding="utf-8",
    )  # fmt: skip
    print(
        f"\nSaved to {out_path}; {len(threads)} test conversations "
        f"{'kept' if args.keep_threads else 'deleted'}."
    )


if __name__ == "__main__":
    main()
