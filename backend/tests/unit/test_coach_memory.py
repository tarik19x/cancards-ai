"""Which checkpointer the coach gets, and that a broken database cannot stop the app."""

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


class _BrokenConnection:
    """Stands in for a Postgres connection that opens but cannot create its tables --
    the exact failure seen with a Neon role that lacks CREATE on the public schema."""

    def __init__(self, fail_on: str):
        self.fail_on = fail_on
        self.closed = False

    async def __aenter__(self):
        if self.fail_on == "connect":
            raise ConnectionError("could not connect to server")
        return self

    async def setup(self):
        raise PermissionError("permission denied for schema public")

    async def __aexit__(self, *exc):
        self.closed = True


@pytest.mark.parametrize("fail_on", ["connect", "setup"])
async def test_a_broken_database_falls_back_to_memory_instead_of_failing_startup(
    monkeypatch, fail_on
):
    monkeypatch.setattr(memory, "get_settings", _settings("postgresql://u:secret@h/db"))
    monkeypatch.setattr(
        memory.AsyncPostgresSaver,
        "from_conn_string",
        lambda url: _BrokenConnection(fail_on),
    )

    async with open_checkpointer() as saver:
        assert isinstance(saver, InMemorySaver)


async def test_the_password_never_reaches_the_log(monkeypatch, capsys):
    monkeypatch.setattr(memory, "get_settings", _settings("postgresql://u:hunter2@h/db"))
    monkeypatch.setattr(
        memory.AsyncPostgresSaver, "from_conn_string", lambda url: _BrokenConnection("connect")
    )

    async with open_checkpointer():
        pass

    output = capsys.readouterr()
    assert "hunter2" not in output.out + output.err


async def test_a_working_database_is_used_and_closed_afterwards(monkeypatch):
    class Working(_BrokenConnection):
        async def setup(self):
            return None

    connection = Working("never")
    monkeypatch.setattr(memory, "get_settings", _settings("postgresql://u:p@h/db"))
    monkeypatch.setattr(memory.AsyncPostgresSaver, "from_conn_string", lambda url: connection)

    async with open_checkpointer() as saver:
        assert saver is connection
        assert not connection.closed

    assert connection.closed


async def test_an_error_inside_the_app_is_not_swallowed_by_the_fallback(monkeypatch):
    # The fallback is for failing to OPEN the database, not for hiding bugs in the app
    # that is running on top of it.
    class Working(_BrokenConnection):
        async def setup(self):
            return None

    monkeypatch.setattr(memory, "get_settings", _settings("postgresql://u:p@h/db"))
    monkeypatch.setattr(memory.AsyncPostgresSaver, "from_conn_string", lambda url: Working("never"))

    with pytest.raises(RuntimeError, match="app bug"):
        async with open_checkpointer():
            raise RuntimeError("app bug")
