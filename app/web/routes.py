"""Pantallas: registro, inicio de sesión y conexión de números de WhatsApp."""
import logging
from pathlib import Path
from typing import Iterator

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import connections as conns
from app.db import Account, Connection, Conversation, Message, session_scope
from app.web import auth

log = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

STATE_LABELS = {
    "creating": "Preparando…",
    "qr": "Esperando que escanees el código",
    "connecting": "Conectando…",
    "open": "Conectado",
    "closed": "Desconectado",
}
templates.env.globals["STATE_LABELS"] = STATE_LABELS


class NotLoggedIn(Exception):
    pass


def get_session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.session_factory) as session:
        yield session


def current_account(request: Request, session: Session = Depends(get_session)) -> Account:
    account_id = request.session.get("account_id")
    account = session.get(Account, account_id) if account_id else None
    if account is None:
        request.session.clear()
        raise NotLoggedIn()
    return account


def _render(request: Request, template: str, status_code: int = 200, **ctx):
    return templates.TemplateResponse(request, template, ctx, status_code=status_code)


def _owned(session: Session, account: Account, connection_id: int) -> Connection:
    conn = conns.get_owned(session, account.id, connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Conexión no encontrada")
    return conn


# --------------------------------------------------------------------------- cuentas
@router.get("/", response_class=HTMLResponse)
def home(request: Request, session: Session = Depends(get_session)):
    account_id = request.session.get("account_id")
    account = session.get(Account, account_id) if account_id else None
    if account is None:
        return RedirectResponse("/login", status_code=303)

    rows = []
    for conn in conns.list_connections(session, account.id):
        n_conv = session.scalar(select(func.count()).select_from(Conversation).where(Conversation.connection_id == conn.id))
        n_msg = session.scalar(
            select(func.count()).select_from(Message).join(Conversation).where(Conversation.connection_id == conn.id)
        )
        rows.append({"conn": conn, "conversations": n_conv, "messages": n_msg})
    return _render(request, "dashboard.html", account=account, rows=rows, max_connections=conns.MAX_CONNECTIONS_PER_ACCOUNT)


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return _render(request, "register.html", error=None, email="", name="")


@router.post("/register", response_class=HTMLResponse)
def register(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    name: str = Form(""),
    session: Session = Depends(get_session),
):
    try:
        account = auth.register(session, email, password, name)
    except ValueError as exc:
        return _render(request, "register.html", status_code=400, error=str(exc), email=email, name=name)
    request.session.clear()
    request.session["account_id"] = account.id
    return RedirectResponse("/", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return _render(request, "login.html", error=None, email="")


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    session: Session = Depends(get_session),
):
    account = auth.authenticate(session, email, password)
    if account is None:
        return _render(request, "login.html", status_code=400, error="Correo o contraseña incorrectos.", email=email)
    request.session.clear()  # evita reutilizar una sesión previa
    request.session["account_id"] = account.id
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# --------------------------------------------------------------------------- conexiones
@router.get("/connections/new", response_class=HTMLResponse)
def connection_form(request: Request, account: Account = Depends(current_account)):
    return _render(request, "connection_new.html", account=account, error=None, phone="")


@router.post("/connections", response_class=HTMLResponse)
async def connection_create(
    request: Request,
    phone: str = Form(""),
    account: Account = Depends(current_account),
    session: Session = Depends(get_session),
):
    try:
        conn = await conns.create_connection(session, request.app.state.evolution, account.id, phone)
    except conns.UserError as exc:
        return _render(request, "connection_new.html", status_code=400, account=account, error=str(exc), phone=phone)
    return RedirectResponse(f"/connections/{conn.id}", status_code=303)


@router.get("/connections/{connection_id}", response_class=HTMLResponse)
def connection_page(
    request: Request,
    connection_id: int,
    account: Account = Depends(current_account),
    session: Session = Depends(get_session),
):
    conn = _owned(session, account, connection_id)
    return _render(request, "connection.html", account=account, conn=conn)


@router.get("/connections/{connection_id}/panel", response_class=HTMLResponse)
async def connection_panel(
    request: Request,
    connection_id: int,
    account: Account = Depends(current_account),
    session: Session = Depends(get_session),
):
    """Fragmento que la página consulta cada pocos segundos para mostrar el estado."""
    conn = _owned(session, account, connection_id)
    if conn.state != "open":
        await conns.sync_state(request.app.state.evolution, conn)
    return _render(request, "_panel.html", conn=conn)


@router.get("/connections/{connection_id}/qr", response_class=HTMLResponse)
async def connection_qr(
    request: Request,
    connection_id: int,
    account: Account = Depends(current_account),
    session: Session = Depends(get_session),
):
    """QR y código de emparejamiento actuales. La página lo renueva antes de que caduque."""
    conn = _owned(session, account, connection_id)
    if conn.state == "open":
        return HTMLResponse("")
    return await _qr_fragment(request, session, conn, retry=False)


@router.post("/connections/{connection_id}/retry", response_class=HTMLResponse)
async def connection_retry(
    request: Request,
    connection_id: int,
    account: Account = Depends(current_account),
    session: Session = Depends(get_session),
):
    conn = _owned(session, account, connection_id)
    return await _qr_fragment(request, session, conn, retry=True)


async def _qr_fragment(request: Request, session: Session, conn: Connection, retry: bool):
    evo = request.app.state.evolution
    try:
        data = await (conns.retry(session, evo, conn) if retry else conns.fresh_qr(evo, conn))
    except Exception as exc:  # noqa: BLE001 - se muestra un mensaje amable en lugar de un error
        log.warning("QR no disponible para %s: %s", conn.instance_name, exc)
        return _render(request, "_qr.html", conn=conn, qr=None, code=None, error=True)
    code = data.get("pairingCode")
    if code and len(code) == 8:
        code = f"{code[:4]}-{code[4:]}"
    return _render(request, "_qr.html", conn=conn, qr=conns.qr_image_src(data), code=code, error=False)


@router.post("/connections/{connection_id}/disconnect")
async def connection_disconnect(
    request: Request,
    connection_id: int,
    account: Account = Depends(current_account),
    session: Session = Depends(get_session),
):
    conn = _owned(session, account, connection_id)
    await conns.disconnect(session, request.app.state.evolution, conn)
    return RedirectResponse("/", status_code=303)
