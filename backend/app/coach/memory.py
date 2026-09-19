"""Conversation memory for the coach: LangGraph checkpointing into Postgres.

LangGraph already knows how to persist a graph's state after every node; all this
module decides is where that goes. With DATABASE_URL set it goes to Postgres, so a
conversation survives a restart or a redeploy. Without it, conversations live in
memory and are lost on restart -- which keeps tests and the existing deployment
(which has no database) working unchanged.

The saver is opened once for the application's lifetime rather than per request:
its connection pool is the expensive part, and a new pool per message would be
both slow and a good way to exhaust Postgres's connection limit.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import get_settings
from app.logging_config import get_logger

log = get_logger(__name__)


@asynccontextmanager
async def open_checkpointer() -> AsyncIterator[Any]:
    """Yield the checkpointer to compile the graph with, and hold it open.

    setup() creates LangGraph's own tables if they are absent. It is safe to run
    on every start -- it is idempotent -- and doing so means a fresh database
    needs no migration step before the first conversation.
    """
    url = get_settings().database_url
    if not url:
        log.warning("conversation_memory_in_process_only", reason="DATABASE_URL not set")
        yield InMemorySaver()
        return

    async with AsyncPostgresSaver.from_conn_string(url) as saver:
        await saver.setup()
        log.info("conversation_memory_ready", backend="postgres")
        yield saver
