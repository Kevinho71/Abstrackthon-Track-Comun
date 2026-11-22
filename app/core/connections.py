"""Alta, reintento y baja de las conexiones de WhatsApp (una instancia de Evolution por número)."""
import logging
import re
import secrets
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config
from app.channels.evolution import EvolutionClient, EvolutionError
from app.db import Connection

log = logging.getLogger(__name__)

MAX_CONNECTIONS_PER_ACCOUNT = 5


class UserError(ValueError):
    """Error con un mensaje apto para mostrar al usuario."""


def normalize_phone(raw: str) -> str:
    """Deja solo los dígitos, con el código de país. Ej.: «+591 7000 0001» -> «59170000001»."""
    digits = re.sub(r"\D", "", raw or "")
    if not 8 <= len(digits) <= 15:
        raise UserError("Escribe el número con el código de país, por ejemplo 59170000001.")
    return digits


def webhook_url() -> str:
    return f"{config.WEBHOOK_BASE_URL}/webhook/evolution"


def list_connections(session: Session, account_id: int) -> list[Connection]:
    return list(
        session.scalars(
            select(Connection).where(Connection.account_id == account_id).order_by(Connection.id)
        )
    )


def get_owned(session: Session, account_id: int, connection_id: int) -> Optional[Connection]:
    conn = session.get(Connection, connection_id)
    return conn if conn and conn.account_id == account_id else None


async def create_connection(session: Session, evo: EvolutionClient, account_id: int, phone_raw: str) -> Connection:
    phone = normalize_phone(phone_raw)
    count = session.scalar(select(func.count()).select_from(Connection).where(Connection.account_id == account_id))
    if count >= MAX_CONNECTIONS_PER_ACCOUNT:
        raise UserError(f"Se permiten hasta {MAX_CONNECTIONS_PER_ACCOUNT} números por cuenta.")
    if session.scalar(select(Connection.id).where(Connection.phone == phone, Connection.state != "closed")):
        raise UserError("Ese número ya está conectado.")

    conn = Connection(
        account_id=account_id,
        instance_name=f"acc{account_id}-{secrets.token_hex(4)}",
        phone=phone,
        state="creating",
    )
    session.add(conn)
    session.flush()
    try:
        await evo.create_instance(conn.instance_name, webhook_url(), number=phone, token=config.WEBHOOK_TOKEN)
    except EvolutionError as exc:
        log.error("No se pudo crear la instancia: %s", exc)
        session.delete(conn)
        session.flush()
        raise UserError("No pudimos iniciar la conexión con WhatsApp. Inténtalo de nuevo en un momento.") from exc
    return conn


async def fresh_qr(evo: EvolutionClient, conn: Connection) -> dict:
    """QR y código de emparejamiento actuales. Si la instancia ya no existe, se vuelve a crear."""
    try:
        return await evo.connect(conn.instance_name)
    except EvolutionError:
        await evo.create_instance(conn.instance_name, webhook_url(), number=conn.phone, token=config.WEBHOOK_TOKEN)
        return await evo.connect(conn.instance_name)


async def retry(session: Session, evo: EvolutionClient, conn: Connection) -> dict:
    """Vuelve a pedir el QR. Reutiliza la misma instancia, sin crear otra conexión."""
    try:
        data = await fresh_qr(evo, conn)
    except EvolutionError as exc:
        raise UserError("No pudimos generar un código nuevo. Inténtalo de nuevo en un momento.") from exc
    if conn.state in ("closed", "creating"):
        conn.state = "qr"
    return data


async def sync_state(evo: EvolutionClient, conn: Connection) -> None:
    """Consulta el estado a Evolution, por si se perdió un webhook."""
    try:
        state = await evo.state(conn.instance_name)
    except EvolutionError:
        return
    mapped = {"open": "open", "connecting": "connecting", "close": "closed"}.get(state)
    if mapped and mapped != conn.state and not (mapped == "connecting" and conn.state == "qr"):
        conn.state = mapped


async def disconnect(session: Session, evo: EvolutionClient, conn: Connection) -> None:
    """Cierra la sesión de WhatsApp y borra la instancia. Los mensajes guardados se conservan."""
    try:
        await evo.delete_instance(conn.instance_name)
    except EvolutionError as exc:
        log.warning("No se pudo borrar la instancia %s: %s", conn.instance_name, exc)
    conn.state = "closed"


def qr_image_src(data: dict) -> Optional[str]:
    b64 = data.get("base64")
    if not b64:
        return None
    return b64 if b64.startswith("data:") else f"data:image/png;base64,{b64}"
