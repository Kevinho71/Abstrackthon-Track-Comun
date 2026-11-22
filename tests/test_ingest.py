from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.channels.evolution import ConnectionUpdate, IncomingMessage
from app.core import ingest
from app.db import Connection, Conversation, Message, session_scope

T0 = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)


def msg(id_="M1", from_me=False, text="hola", at=T0, jid="59170000001@s.whatsapp.net", name="Ana"):
    return IncomingMessage("inst1", jid, id_, from_me, text, "text", at, name)


def count(s, model):
    return s.scalar(select(func.count()).select_from(model))


def test_mensaje_repetido_se_guarda_una_vez(factory, connection):
    with session_scope(factory) as s:
        conn = s.get(Connection, connection)
        assert ingest.ingest_message(s, conn, msg()) is True
        assert ingest.ingest_message(s, conn, msg()) is False
    with session_scope(factory) as s:
        assert count(s, Message) == 1 and count(s, Conversation) == 1


def test_conversacion_unica_por_cliente_y_nombre(factory, connection):
    with session_scope(factory) as s:
        conn = s.get(Connection, connection)
        ingest.ingest_message(s, conn, msg("A", at=T0))
        ingest.ingest_message(s, conn, msg("B", at=T0 + timedelta(minutes=1), text="otra"))
        ingest.ingest_message(s, conn, msg("C", at=T0, jid="59170000002@s.whatsapp.net", name="Beto"))
    with session_scope(factory) as s:
        assert count(s, Conversation) == 2
        conv = s.scalar(select(Conversation).where(Conversation.remote_jid.like("59170000001%")))
        assert conv.customer_name == "Ana" and len(conv.messages) == 2


def test_unanswered_sigue_al_ultimo_mensaje(factory, connection):
    with session_scope(factory) as s:
        conn = s.get(Connection, connection)
        ingest.ingest_message(s, conn, msg("A", at=T0))
        conv = s.scalar(select(Conversation))
        assert conv.unanswered is True
        ingest.ingest_message(s, conn, msg("B", from_me=True, at=T0 + timedelta(minutes=2), name="Yo"))
        assert conv.unanswered is False
        assert conv.customer_name == "Ana"  # el nombre del propio negocio no sobrescribe al cliente


def test_mensaje_antiguo_no_cambia_quien_hablo_ultimo(factory, connection):
    with session_scope(factory) as s:
        conn = s.get(Connection, connection)
        ingest.ingest_message(s, conn, msg("B", from_me=True, at=T0 + timedelta(minutes=5)))
        ingest.ingest_message(s, conn, msg("A", at=T0))  # llegó tarde, pero es anterior
        conv = s.scalar(select(Conversation))
        assert conv.unanswered is False
        assert conv.last_message_at == T0 + timedelta(minutes=5)


def test_cliente_que_vuelve_a_escribir_reabre_la_conversacion(factory, connection):
    with session_scope(factory) as s:
        conn = s.get(Connection, connection)
        ingest.ingest_message(s, conn, msg("A", at=T0))
        conv = s.scalar(select(Conversation))
        conv.done = True
        ingest.ingest_message(s, conn, msg("B", at=T0 + timedelta(days=1)))
        assert conv.done is False and conv.unanswered is True


def test_estado_de_conexion(factory, connection):
    with session_scope(factory) as s:
        conn = ingest.apply_connection_update(s, ConnectionUpdate("inst1", "open"))
        assert conn.state == "open" and conn.connected_at is not None
        conn = ingest.apply_connection_update(s, ConnectionUpdate("inst1", "close"))
        assert conn.state == "closed"
        assert ingest.apply_connection_update(s, ConnectionUpdate("otra", "open")) is None


def test_needs_analysis(factory, connection):
    with session_scope(factory) as s:
        conn = s.get(Connection, connection)
        ingest.ingest_message(s, conn, msg("A", at=T0))
        conv = s.scalar(select(Conversation))
        assert ingest.needs_analysis(conv, T0 + timedelta(minutes=10)) is True
        assert ingest.needs_analysis(conv, T0 - timedelta(minutes=1)) is False  # aún no hay silencio
        conv.last_analyzed_at = T0 + timedelta(minutes=11)
        assert ingest.needs_analysis(conv, T0 + timedelta(minutes=12)) is False
