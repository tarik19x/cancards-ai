"""Which checkpointer the coach gets, and that a broken database cannot stop the app."""

import asyncio
import os
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.coach import memory
from app.coach.memory import open_checkpointer


def _settings(url: str):
    return lambda: SimpleNamespace(database_url=url)


async def test_without_a_database_url_conversations_stay_in_memory(monkeypatch):
    monkeypatch.setattr(memory, "get_settings", _settings(""))
    async with open_checkpointer() as saver:
        assert isinstance(saver, InMemorySaver)


class _FakePool:
    """Stands in for the connection pool. Opening it can fail, as with a Neon outage."""

    @staticmethod
    async def check_connection(conn):  # the code reads this off the pool class
        return None

    def __init__(self, fail_on_open: bool = False):
        self.fail_on_open = fail_on_open
        self.closed = False

    async def open(self, **kwargs):
        if self.fail_on_open:
            raise ConnectionError("could not connect to server")

    async def close(self):
        self.closed = True


class _FakeSaver:
    """Stands in for the saver. setup() fails the way a Neon role without CREATE does."""

    def __init__(self, pool, fail_on_setup: bool = False):
        self.pool = pool
        self.fail_on_setup = fail_on_setup

    async def setup(self):
        if self.fail_on_setup:
            raise PermissionError("permission denied for schema public")


def _fake_database(monkeypatch, fail_on: str | None):
    """Patch the pool and saver; returns the pool so a test can see whether it was closed."""
    pool = _FakePool(fail_on_open=fail_on == "connect")

    class PoolClass:
        check_connection = _FakePool.check_connection

        def __new__(cls, *args, **kwargs):
            return pool

    monkeypatch.setattr(memory, "AsyncConnectionPool", PoolClass)
    monkeypatch.setattr(
        memory, "AsyncPostgresSaver", lambda p: _FakeSaver(p, fail_on_setup=fail_on == "setup")
    )
    return pool


@pytest.mark.parametrize("fail_on", ["connect", "setup"])
async def test_a_broken_database_falls_back_to_memory_instead_of_failing_startup(
    monkeypatch, fail_on
):
    monkeypatch.setattr(memory, "get_settings", _settings("postgresql://u:secret@h/db"))
    pool = _fake_database(monkeypatch, fail_on)

    async with open_checkpointer() as saver:
        assert isinstance(saver, InMemorySaver)

    assert pool.closed  # a failed start must not leave a pool retrying in the background


async def test_the_password_never_reaches_the_log(monkeypatch, capsys):
    monkeypatch.setattr(memory, "get_settings", _settings("postgresql://u:hunter2@h/db"))
    _fake_database(monkeypatch, "connect")

    async with open_checkpointer():
        pass

    output = capsys.readouterr()
    assert "hunter2" not in output.out + output.err


async def test_a_working_database_is_used_and_closed_afterwards(monkeypatch):
    monkeypatch.setattr(memory, "get_settings", _settings("postgresql://u:p@h/db"))
    pool = _fake_database(monkeypatch, None)

    async with open_checkpointer() as saver:
        assert isinstance(saver, _FakeSaver)
        assert saver.pool is pool
        assert not pool.closed

    assert pool.closed


async def test_the_pool_tests_each_connection_before_using_it(monkeypatch):
    # This is the fix for "the connection is closed": Neon drops idle connections, and only
    # a pool that checks a connection before handing it out replaces the dead one.
    seen = {}

    class RecordingPool(_FakePool):
        def __init__(self, url, **kwargs):
            super().__init__()
            seen.update(kwargs)

    monkeypatch.setattr(memory, "get_settings", _settings("postgresql://u:p@h/db"))
    monkeypatch.setattr(memory, "AsyncConnectionPool", RecordingPool)
    monkeypatch.setattr(memory, "AsyncPostgresSaver", lambda p: _FakeSaver(p))

    async with open_checkpointer():
        pass

    assert seen["check"] is RecordingPool.check_connection
    # The saver needs autocommit and no prepared statements on every connection it is given.
    assert seen["kwargs"]["autocommit"] is True
    assert seen["kwargs"]["prepare_threshold"] == 0


async def test_an_error_inside_the_app_is_not_swallowed_by_the_fallback(monkeypatch):
    # The fallback is for failing to OPEN the database, not for hiding bugs in the app
    # that is running on top of it.
    monkeypatch.setattr(memory, "get_settings", _settings("postgresql://u:p@h/db"))
    _fake_database(monkeypatch, None)

    with pytest.raises(RuntimeError, match="app bug"):
        async with open_checkpointer():
            raise RuntimeError("app bug")


@pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRES_URL"),
    reason="needs a throwaway Postgres in TEST_POSTGRES_URL; skipped in CI and clean checkouts",
)
def test_a_dropped_connection_is_replaced_not_fatal(monkeypatch):
    """The real failure: the server closes the connection while the app is idle.

    Runs against a real Postgres. It kills the pool's connection from the server side,
    exactly what Neon's idle suspend does, then checks the next read still works.
    """
    import psycopg

    url = os.environ["TEST_POSTGRES_URL"]
    monkeypatch.setattr(memory, "get_settings", _settings(url))
    config = {"configurable": {"thread_id": "reconnect-test", "checkpoint_ns": ""}}

    async def scenario():
        async with open_checkpointer() as saver:
            assert await saver.aget_tuple(config) is None  # works before the drop

            async with await psycopg.AsyncConnection.connect(url, autocommit=True) as admin:
                await admin.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE pid <> pg_backend_pid() AND datname = current_database()"
                )

            # The pool replaced the dead connection instead of raising "the connection is closed".
            assert await saver.aget_tuple(config) is None

    # psycopg's async mode needs the selector loop; Windows defaults to the proactor loop.
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        runner.run(scenario())
