"""Cliente HTTP de Evolution API y lectura de sus eventos de webhook.

Los formatos de petición y de evento siguen la API v2 de Evolution. Se verifican contra la
versión desplegada en la Fase 0 (ver docs/prueba-evolution.md).
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)

WEBHOOK_EVENTS = ["MESSAGES_UPSERT", "CONNECTION_UPDATE", "QRCODE_UPDATED"]
_IGNORED_TYPES = {"reactionMessage", "protocolMessage", "senderKeyDistributionMessage"}
_WRAPPERS = ("ephemeralMessage", "viewOnceMessage", "viewOnceMessageV2", "documentWithCaptionMessage")


# --------------------------------------------------------------------------- cliente
class EvolutionError(RuntimeError):
    pass


class EvolutionClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 20.0,
                 transport: Optional[httpx.AsyncBaseTransport] = None):
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"apikey": api_key},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            resp = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise EvolutionError(f"No se pudo conectar con Evolution: {exc}") from exc
        if resp.status_code >= 400:
            raise EvolutionError(f"Evolution respondió {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else {}

    @staticmethod
    def _webhook_config(url: str, token: Optional[str]) -> dict:
        cfg: dict[str, Any] = {"url": url, "byEvents": False, "base64": False, "events": WEBHOOK_EVENTS}
        if token:  # el token viaja en una cabecera para que no quede en los logs de acceso
            cfg["headers"] = {"x-webhook-token": token, "Content-Type": "application/json"}
        return cfg

    async def create_instance(self, name: str, webhook_url: str, number: Optional[str] = None,
                              token: Optional[str] = None) -> dict:
        body: dict[str, Any] = {
            "instanceName": name,
            "integration": "WHATSAPP-BAILEYS",
            "qrcode": True,
            "webhook": self._webhook_config(webhook_url, token),
        }
        if number:
            body["number"] = number  # con el número, Evolution también genera el código de emparejamiento
        return await self._request("POST", "/instance/create", json=body)

    async def set_webhook(self, name: str, webhook_url: str, token: Optional[str] = None) -> dict:
        body = {"webhook": {"enabled": True, **self._webhook_config(webhook_url, token)}}
        return await self._request("POST", f"/webhook/set/{name}", json=body)

    async def connect(self, name: str, number: Optional[str] = None) -> dict:
        """Devuelve el QR (`base64`, `code`) y, si se pasa el número, el código de emparejamiento."""
        params = {"number": number} if number else None
        return await self._request("GET", f"/instance/connect/{name}", params=params)

    async def state(self, name: str) -> str:
        data = await self._request("GET", f"/instance/connectionState/{name}")
        return (data.get("instance") or {}).get("state") or data.get("state") or "unknown"

    async def logout(self, name: str) -> dict:
        return await self._request("DELETE", f"/instance/logout/{name}")

    async def delete_instance(self, name: str) -> dict:
        return await self._request("DELETE", f"/instance/delete/{name}")


# --------------------------------------------------------------------------- eventos
@dataclass
class IncomingMessage:
    instance: str
    remote_jid: str
    wa_message_id: str
    from_me: bool
    text: str
    type: str
    sent_at: datetime
    push_name: Optional[str] = None


@dataclass
class ConnectionUpdate:
    instance: str
    state: str


def normalize_event(name: str) -> str:
    """`MESSAGES_UPSERT` y `messages.upsert` son el mismo evento."""
    return (name or "").strip().lower().replace("_", ".")


def is_individual_chat(jid: str) -> bool:
    """Solo chats uno a uno. Se descartan grupos, estados, difusiones y canales."""
    return jid.endswith("@s.whatsapp.net") or jid.endswith("@lid")


def phone_from_jid(jid: str) -> Optional[str]:
    if jid.endswith("@s.whatsapp.net"):
        return jid.split("@", 1)[0]
    return None


def _unwrap(message: dict) -> dict:
    for _ in range(3):
        for key in _WRAPPERS:
            inner = message.get(key)
            if isinstance(inner, dict) and isinstance(inner.get("message"), dict):
                message = inner["message"]
                break
        else:
            return message
    return message


def extract_text(message: Any) -> Optional[tuple[str, str]]:
    """Devuelve (texto, tipo) o None si el mensaje no aporta contenido a la conversación."""
    if not isinstance(message, dict):
        return None
    message = _unwrap(message)
    if not message or any(k in message for k in _IGNORED_TYPES):
        return None

    if message.get("conversation"):
        return message["conversation"], "text"
    ext = message.get("extendedTextMessage")
    if isinstance(ext, dict) and ext.get("text"):
        return ext["text"], "text"

    def with_caption(label: str, key: str, kind: str):
        part = message.get(key)
        if not isinstance(part, dict):
            return None
        caption = (part.get("caption") or part.get("fileName") or "").strip()
        return (f"[{label}] {caption}".strip(), kind)

    for label, key, kind in (
        ("imagen", "imageMessage", "image"),
        ("video", "videoMessage", "video"),
        ("documento", "documentMessage", "document"),
    ):
        found = with_caption(label, key, kind)
        if found:
            return found
    if "audioMessage" in message:
        return "[audio]", "audio"
    if "stickerMessage" in message:
        return "[sticker]", "sticker"
    if "locationMessage" in message:
        return "[ubicación]", "location"
    if "contactMessage" in message or "contactsArrayMessage" in message:
        return "[contacto]", "contact"
    return None


def _timestamp(value: Any) -> datetime:
    try:
        if isinstance(value, dict):  # protobuf Long: {"low": ..., "high": ...}
            value = value.get("low")
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return datetime.now(timezone.utc)


def parse_messages_upsert(payload: dict) -> list[IncomingMessage]:
    instance = payload.get("instance") or ""
    data = payload.get("data")
    items = data if isinstance(data, list) else [data]
    out: list[IncomingMessage] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = item.get("key") or {}
        jid, msg_id = key.get("remoteJid") or "", key.get("id") or ""
        if not jid or not msg_id or not is_individual_chat(jid):
            continue
        extracted = extract_text(item.get("message"))
        if not extracted:
            continue
        text, kind = extracted
        out.append(
            IncomingMessage(
                instance=instance,
                remote_jid=jid,
                wa_message_id=msg_id,
                from_me=bool(key.get("fromMe")),
                text=text,
                type=kind,
                sent_at=_timestamp(item.get("messageTimestamp")),
                push_name=item.get("pushName") or None,
            )
        )
    return out


def parse_connection_update(payload: dict) -> Optional[ConnectionUpdate]:
    data = payload.get("data") or {}
    state = data.get("state") if isinstance(data, dict) else None
    instance = payload.get("instance") or (data.get("instance") if isinstance(data, dict) else "")
    if not state or not isinstance(instance, str) or not instance:
        return None
    return ConnectionUpdate(instance=instance, state=state)
