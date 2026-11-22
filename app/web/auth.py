"""Contraseñas con scrypt (biblioteca estándar) y utilidades de cuentas."""
import base64
import hashlib
import hmac
import os
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Account

_N, _R, _P = 2**14, 8, 1
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        _N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# Hash de relleno: permite verificar una contraseña aunque el correo no exista,
# para que el tiempo de respuesta no revele qué correos están registrados.
_DUMMY_HASH = hash_password("relleno-no-valido")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def valid_email(email: str) -> bool:
    return bool(_EMAIL.match(email)) and len(email) <= 255


def register(session: Session, email: str, password: str, name: str | None) -> Account:
    """Crea la cuenta. Lanza ValueError con un mensaje apto para mostrar al usuario."""
    email = normalize_email(email)
    if not valid_email(email):
        raise ValueError("Escribe un correo válido.")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"La contraseña debe tener al menos {MIN_PASSWORD} caracteres.")
    if session.scalar(select(Account.id).where(Account.email == email)):
        raise ValueError("Ya existe una cuenta con ese correo.")
    account = Account(email=email, password_hash=hash_password(password), name=(name or "").strip() or None)
    session.add(account)
    session.flush()
    return account


def authenticate(session: Session, email: str, password: str) -> Account | None:
    account = session.scalar(select(Account).where(Account.email == normalize_email(email)))
    ok = verify_password(password, account.password_hash if account else _DUMMY_HASH)
    return account if (account and ok) else None
