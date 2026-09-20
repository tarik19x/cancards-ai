"""Run the API for a load test: same app and database, per-IP rate limit switched off.

The coach allows 30 chat requests a minute per IP. A load test sends every simulated user from
one machine, so it would be limited to 30 requests a minute and measure the limiter instead of
the app. Real users arrive from different addresses; this stands in for that.

Retrieval is forced to dense so startup does not read the corpus from Pinecone: the coach does
not retrieve, and a load test of it should not spend that quota.

  uv run python ../tests/evals/serve_unlimited.py --port 8001
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
os.environ["RETRIEVAL_MODE"] = "dense"
os.environ["LANGSMITH_TRACING"] = "false"

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402
from app.routers import ask  # noqa: E402

ask.limiter.enabled = False


def _expose_usage() -> None:
    """A test-only route so the load test can read what its requests cost. It is added here,
    not in the app, so the deployed API never exposes spend."""
    from app.clients.usage import meter

    async def usage() -> dict:
        return meter.snapshot()

    app.add_api_route("/_usage", usage, methods=["GET"], include_in_schema=False)


_expose_usage()


def _install_fake_model(delay: float) -> None:
    """Replace Claude with a stub that answers the load test's script, after `delay` seconds.

    Everything else stays real: the graph, the checkpointer and Neon. Used to measure what the
    app itself costs per turn without paying for model calls, and to show how much of a
    measured latency is the model versus the app.
    """
    import json
    import re

    from app.coach import graph as graph_module
    from app.coach import profile as profile_module

    async def fake(system: str, user: str, max_tokens: int = 2000) -> str:
        await asyncio.sleep(delay)
        if not system.startswith("You read a conversation"):
            return "This is a stub answer."
        raw = re.search(r"Conversation \(.*?\):\n(.*)\n\nReturn the updated", user, re.DOTALL)
        messages = json.loads(raw.group(1)) if raw else []
        text = " ".join(m["content"] for m in messages if m["role"] == "user").lower()
        facts: dict[str, object] = {}
        if "3 cards" in text:
            facts["card_count"] = 3
        if "$4000" in text:
            facts |= {"typical_balance_cad": 4000, "total_credit_limit_cad": 10000}
        if "since 2019" in text:
            facts["history_length"] = "over7"
        if "never late" in text:
            facts["missed_payments"] = "never"
        if messages and messages[-1]["content"].strip().lower() == "none":
            facts["recent_inquiries"] = 0
        return json.dumps(facts)

    profile_module.generate_answer = fake
    graph_module.generate_answer = fake


if "FAKE_MODEL_DELAY" in os.environ:
    _install_fake_model(float(os.environ["FAKE_MODEL_DELAY"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    config = uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning", loop="none")
    # Async psycopg (the Postgres checkpointer) refuses Windows' default event loop, so the
    # selector loop is chosen explicitly rather than relying on uvicorn's --reload side effect.
    asyncio.run(uvicorn.Server(config).serve(), loop_factory=asyncio.SelectorEventLoop)


if __name__ == "__main__":
    main()
