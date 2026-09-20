"""Disk cache for dev-script Claude calls.

The question generator re-runs often while its prompts are being tuned, and
each run used to re-pay for every draft even when the prompt for that chunk
hadn't changed. Keyed on model + full prompt, so editing a prompt misses
naturally and unchanged ones are free. It also makes a run reproducible: the
app's Claude calls set no temperature, so an uncached rerun drafts different
questions, which is unwanted for a set that is meant to be frozen.

Dev scripts only. Nothing under app/ imports this.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.clients.usage import meter
from app.config import get_settings

CACHE_PATH = Path(__file__).resolve().parents[1] / "data" / "cache" / "llm_responses.json"

Generate = Callable[..., Awaitable[str]]


class BudgetExceeded(Exception):
    """Raised instead of making a paid call past the cap. Everything paid for
    so far is already on disk, so a rerun resumes without repaying it."""


class CachedGenerator:
    def __init__(self, generate: Generate, path: Path = CACHE_PATH):
        self._generate = generate
        self._path = path
        self._store: dict[str, str] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        )
        self.calls_made = 0
        self.cache_hits = 0
        # A candidate loop that rejects most of what it tries (disambiguation
        # spends two calls per rejection) can otherwise run for thousands of
        # calls before anyone notices.
        self.max_paid_calls: int | None = None
        # A dollar cap on top of the call cap: calls differ a lot in size, and an estimate of
        # 'about N calls' was what underestimated the bill. The meter counts real tokens.
        self.max_cost_usd: float | None = None

    @staticmethod
    def _key(model: str, system: str, user: str, max_tokens: int) -> str:
        blob = json.dumps([model, system, user, max_tokens])
        return hashlib.sha256(blob.encode()).hexdigest()

    async def __call__(self, system: str, user: str, max_tokens: int = 2000) -> str:
        key = self._key(get_settings().llm_model, system, user, max_tokens)
        if key in self._store:
            self.cache_hits += 1
            return self._store[key]
        if self.max_paid_calls is not None and self.calls_made >= self.max_paid_calls:
            raise BudgetExceeded(f"stopped at {self.calls_made} paid calls")
        if self.max_cost_usd is not None and meter.cost_usd >= self.max_cost_usd:
            raise BudgetExceeded(f"stopped at ${meter.cost_usd:.2f} spent")
        raw = await self._generate(system, user, max_tokens=max_tokens)
        self.calls_made += 1
        self._store[key] = raw
        self._save()
        return raw

    def _save(self) -> None:
        # Saved after every paid call, not once at the end: a crash or Ctrl-C
        # partway through a run must not throw away the calls already paid for.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._store), encoding="utf-8")
        tmp.replace(self._path)
