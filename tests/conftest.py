import pytest

from app import config
from app.db import Account, Connection, init_db, make_engine, make_session_factory, session_scope

TOKEN = "token-de-prueba"


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", TOKEN)


@pytest.fixture
def factory(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    yield make_session_factory(engine)
    engine.dispose()


@pytest.fixture
def connection(factory):
    with session_scope(factory) as s:
        acc = Account(email="a@b.c", password_hash="x")
        s.add(acc)
        s.flush()
        conn = Connection(account_id=acc.id, instance_name="inst1", state="open")
        s.add(conn)
        s.flush()
        return conn.id
