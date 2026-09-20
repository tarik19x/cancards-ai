"""What the Claude calls in this process have cost, from the token counts the API returns.

Estimating spend by counting calls was wrong by a factor of three or more: it left out the input
tokens, and the extraction prompt alone is about 900 of them on every call. The API reports exact
token counts for each response, so this adds them up and prices them.

The prices are Anthropic's published per-million-token rates as of mid-2026 and are the one part
that can go stale: check them against the pricing page before quoting a figure. A model that is
not in the table is priced like Sonnet 4.6 and flagged as assumed, so the total is never silently
zero.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# (input, output) US dollars per million tokens.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
}
ASSUMED_MODEL = "claude-sonnet-4-6"
CACHE_READ_MULTIPLIER = 0.10  # reading a cached prefix costs a tenth of normal input
CACHE_WRITE_MULTIPLIER = 1.25  # writing it the first time costs a quarter more (5-minute TTL)

# Outside the repo's tracked files: data/cache is gitignored.
USAGE_LOG = Path(__file__).resolve().parents[2] / "data" / "cache" / "usage_log.jsonl"


@dataclass
class UsageMeter:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    assumed_models: set[str] = field(default_factory=set)

    def record(self, model: str, usage: Any) -> None:
        """Add one response's usage. Missing counts (some responses omit cache fields) are 0."""
        fresh = getattr(usage, "input_tokens", 0) or 0
        out = getattr(usage, "output_tokens", 0) or 0
        written = getattr(usage, "cache_creation_input_tokens", 0) or 0
        read = getattr(usage, "cache_read_input_tokens", 0) or 0
        if model not in PRICES_PER_MTOK:
            self.assumed_models.add(model)
        price_in, price_out = PRICES_PER_MTOK.get(model, PRICES_PER_MTOK[ASSUMED_MODEL])
        self.calls += 1
        self.input_tokens += fresh
        self.output_tokens += out
        self.cache_write_tokens += written
        self.cache_read_tokens += read
        self.cost_usd += (
            fresh * price_in
            + written * price_in * CACHE_WRITE_MULTIPLIER
            + read * price_in * CACHE_READ_MULTIPLIER
            + out * price_out
        ) / 1_000_000

    def reset(self) -> None:
        self.__init__()  # type: ignore[misc]

    def snapshot(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cost_usd": round(self.cost_usd, 4),
            "prices_assumed_for": sorted(self.assumed_models),
        }

    def summary(self) -> str:
        cache = ""
        prompt_total = self.input_tokens + self.cache_read_tokens + self.cache_write_tokens
        if self.cache_read_tokens or self.cache_write_tokens:
            share = self.cache_read_tokens / prompt_total if prompt_total else 0
            cache = f", {share:.0%} of input read from cache"
        note = " (price assumed for an unlisted model)" if self.assumed_models else ""
        return (
            f"Claude usage: {self.calls} paid calls, {self.input_tokens:,} fresh input + "
            f"{self.output_tokens:,} output tokens{cache} -> about ${self.cost_usd:.2f}{note}"
        )

    def append_to_log(self, label: str, path: Path | None = None) -> None:
        """One line per run in a local file, so 'what have I spent today' has an answer."""
        target = path or USAGE_LOG
        target.parent.mkdir(parents=True, exist_ok=True)
        entry = {"at": datetime.now(UTC).isoformat(), "label": label, **self.snapshot()}
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")


# One meter per process: every generate_answer / stream_answer call adds to it.
meter = UsageMeter()
