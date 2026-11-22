"""Receptor de eventos de Evolution API."""
import hmac
import logging

from fastapi import APIRouter, HTTPException, Request

from app import config
from app.channels import evolution
from app.core import ingest
from app.db import session_scope

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/webhook/evolution")
def evolution_webhook(request: Request, payload: dict, token: str = ""):
    # Función síncrona: FastAPI la ejecuta en un hilo, así la base de datos no bloquea el servidor.
    if not config.WEBHOOK_TOKEN or not hmac.compare_digest(token, config.WEBHOOK_TOKEN):
        raise HTTPException(status_code=401, detail="token inválido")

    event = evolution.normalize_event(payload.get("event", ""))
    instance = payload.get("instance") or ""
    factory = request.app.state.session_factory

    with session_scope(factory) as session:
        connection = ingest.get_connection(session, instance)
        if connection is None:
            log.warning("Evento %s de una instancia desconocida: %s", event, instance)
            return {"ok": True, "ignored": "instancia desconocida"}

        if event == "messages.upsert":
            saved = sum(
                ingest.ingest_message(session, connection, msg)
                for msg in evolution.parse_messages_upsert(payload)
            )
            return {"ok": True, "saved": saved}

        if event == "connection.update":
            update = evolution.parse_connection_update(payload)
            if update:
                ingest.apply_connection_update(session, update)
            return {"ok": True}

        if event == "qrcode.updated":
            if connection.state in ("creating", "closed"):
                connection.state = "qr"
            return {"ok": True}

    return {"ok": True, "ignored": event}
