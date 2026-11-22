from datetime import timedelta

import pytest

from app.db import Database, now_utc


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "t.db"))
    d.upsert_agent(1, "Laura")
    return d


def _add(db, status="pendiente_seguimiento", follow_up=None, unanswered=False):
    return db.add_chat(1, "Marta", "resumen", status, None, None, follow_up, unanswered)


def test_chat_cerrado_sin_pendientes_queda_hecho(db):
    cid = _add(db, status="vendida")
    assert db.get_chat(cid, 1)["done"] == 1
    assert db.pending(1) == []


def test_recordatorio_vencido_respeta_enfriamiento(db):
    cid = _add(db, follow_up=now_utc() - timedelta(minutes=5))
    assert [r["id"] for r in db.due_reminders(120)] == [cid]
    db.mark_reminded(cid)
    assert db.due_reminders(120) == []


def test_seguimiento_futuro_no_dispara(db):
    _add(db, follow_up=now_utc() + timedelta(hours=3))
    assert db.due_reminders(120) == []


def test_sin_responder_dispara_y_hecho_lo_apaga(db):
    cid = _add(db, unanswered=True)
    assert len(db.due_reminders(120)) == 1
    assert db.mark_done(cid, 1)
    assert db.due_reminders(120) == []


def test_otro_agente_no_puede_modificar(db):
    cid = _add(db)
    assert not db.mark_done(cid, 999)
    assert not db.set_status(cid, 999, "vendida")
