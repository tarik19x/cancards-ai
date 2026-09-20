"""Conversation memory for the coach: LangGraph checkpointing into Postgres.

LangGraph already knows how to persist a graph's state after every node; all this
module decides is where that goes. With DATABASE_URL set it goes to Postgres, so a
conversation survives a restart or a redeploy. Without it, conversations live in
memory and are lost on restart -- which keeps tests and the existing deployment
(which has no database) working unchanged.

If Postgres is configured but cannot be used (wrong role, network, quota), the coach
falls back to memory and says so loudly in the log, rather than refusing to start.
The coach is one feature of the app; a database problem must not take the card
search and the ask page down with it.

The saver is opened once for the application's lifetime rather than per request: a new
connection per message would be slow and a good way to exhaust Postgres's connection limit.

It holds ONE connection, and LangGraph's saver runs one database operation at a time on it
(an asyncio lock around every cursor). Concurrent conversations therefore queue behind each
other, so the number of database operations per turn is what sets the latency under load.
The chat endpoint saves once per turn (durability="exit") for that reason. A connection pool
was tried and made no measurable difference: the saver's lock, not the connection count,
is the limit.
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

    connection = AsyncPostgresSaver.from_conn_string(url)
    try:
        saver = await connection.__aenter__()
        await saver.setup()
    except Exception as exc:
        # Deliberately broad: whatever went wrong, the answer is the same. The message
        # is logged but never the URL, which carries the password.
        log.error(
            "conversation_memory_postgres_unavailable",
            error=type(exc).__name__,
            detail=str(exc)[:200],
            effect="conversations will be lost on restart",
        )
        yield InMemorySaver()
        return

    log.info("conversation_memory_ready", backend="postgres")
    try:
        yield saver
    finally:
        await connection.__aexit__(None, None, None)
