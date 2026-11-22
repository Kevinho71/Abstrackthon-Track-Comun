import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app import config, llm
from app.db import CLOSED_STATUSES, STATUSES, Database
from app.parser import parse

log = logging.getLogger(__name__)

LABELS = {
    "vendida": "💰 Vendida",
    "cita_agendada": "📅 Cita agendada",
    "pendiente_seguimiento": "⏳ Pendiente",
    "resuelta": "✅ Resuelta",
    "perdida": "❌ Perdida",
}

HELP = (
    "Hola, soy tu asistente de seguimiento de chats.\n\n"
    "1) Envíame un chat exportado de WhatsApp (.txt) o pega la conversación aquí.\n"
    "2) Te devuelvo el resumen, el estado y la siguiente acción.\n"
    "3) Te recuerdo los pendientes y las preguntas sin responder.\n\n"
    "Comandos:\n"
    "/pendientes - chats por atender\n"
    "/resumen - conteo por estado\n"
    "/hecho <id> - marcar un chat como hecho\n"
    "/nombre <tu nombre en WhatsApp> - para saber quién habló último\n"
    "/ayuda - este mensaje"
)


def _db(ctx: ContextTypes.DEFAULT_TYPE) -> Database:
    return ctx.application.bot_data["db"]


def _allowed(update: Update) -> bool:
    if not config.ALLOWED_USER_IDS:
        return True
    user = update.effective_user
    return bool(user and user.id in config.ALLOWED_USER_IDS)


def _fmt_dt(utc_iso: str | None) -> str:
    if not utc_iso:
        return "—"
    dt = datetime.fromisoformat(utc_iso).astimezone(config.LOCAL_TZ)
    return dt.strftime("%d/%m %H:%M")


def card_text(row) -> str:
    lines = [
        f"#{row['id']} · {row['customer']}",
        f"Estado: {LABELS.get(row['status'], row['status'])}",
        f"Resumen: {row['summary']}",
    ]
    if row["next_action"]:
        lines.append(f"Siguiente acción: {row['next_action']}")
    if row["follow_up_at"]:
        lines.append(f"Seguimiento: {_fmt_dt(row['follow_up_at'])}")
    if row["amount"]:
        lines.append(f"Monto: {row['amount']:g}")
    if row["unanswered"]:
        lines.append("⚠️ El cliente espera respuesta")
    return "\n".join(lines)


def card_keyboard(chat_id: int, reminder: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if reminder:
        rows.append(
            [
                InlineKeyboardButton("✅ Hecho", callback_data=f"done|{chat_id}"),
                InlineKeyboardButton("⏰ En 1 h", callback_data=f"snz|{chat_id}"),
            ]
        )
    else:
        rows.append([InlineKeyboardButton("✅ Marcar hecho", callback_data=f"done|{chat_id}")])
        rows.append(
            [
                InlineKeyboardButton(LABELS[s], callback_data=f"st|{chat_id}|{s}")
                for s in STATUSES[:3]
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(LABELS[s], callback_data=f"st|{chat_id}|{s}")
                for s in STATUSES[3:]
            ]
        )
    return InlineKeyboardMarkup(rows)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    user = update.effective_user
    _db(ctx).upsert_agent(user.id, user.full_name)
    await update.message.reply_text(HELP)


async def nombre(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    name = " ".join(ctx.args).strip()
    if not name:
        await update.message.reply_text("Uso: /nombre <tu nombre tal como aparece en el chat de WhatsApp>")
        return
    user = update.effective_user
    _db(ctx).upsert_agent(user.id, user.full_name)
    _db(ctx).set_wa_name(user.id, name)
    await update.message.reply_text(f"Listo. Te identifico como «{name}» en los chats.")


async def pendientes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    rows = _db(ctx).pending(update.effective_user.id)
    if not rows:
        await update.message.reply_text("No tienes pendientes. 🎉")
        return
    lines = []
    for r in rows:
        flag = "⚠️" if r["unanswered"] else "•"
        lines.append(
            f"{flag} #{r['id']} {r['customer']} · {LABELS.get(r['status'])} · seguimiento {_fmt_dt(r['follow_up_at'])}"
        )
    await update.message.reply_text("Pendientes:\n" + "\n".join(lines) + "\n\n/hecho <id> para cerrar uno.")


async def resumen(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    s = _db(ctx).stats(update.effective_user.id)
    lines = [f"{LABELS[k]}: {s.get(k, 0)}" for k in STATUSES]
    lines.append(f"⚠️ Sin responder: {s.get('_sin_responder', 0)}")
    await update.message.reply_text("\n".join(lines))


async def hecho(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    try:
        chat_id = int(ctx.args[0].lstrip("#"))
    except (IndexError, ValueError):
        await update.message.reply_text("Uso: /hecho <id>")
        return
    ok = _db(ctx).mark_done(chat_id, update.effective_user.id)
    await update.message.reply_text("Marcado como hecho ✅" if ok else "No encontré ese chat.")


async def _process(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str):
    user = update.effective_user
    db = _db(ctx)
    db.upsert_agent(user.id, user.full_name)
    agent = db.get_agent(user.id)
    parsed = parse(text)
    status_msg = await update.message.reply_text("Analizando el chat…")
    try:
        now_local = datetime.now(timezone.utc).astimezone(config.LOCAL_TZ)
        a = await llm.analyze(parsed.transcript, now_local)
    except Exception:
        log.exception("Falló el análisis")
        await status_msg.edit_text("No pude analizar el chat ahora. Intenta de nuevo en un momento.")
        return

    follow_up = None
    if a.fecha_seguimiento:
        try:
            naive = datetime.fromisoformat(a.fecha_seguimiento)
            follow_up = naive.replace(tzinfo=config.LOCAL_TZ) if naive.tzinfo is None else naive
        except ValueError:
            follow_up = None

    unanswered = a.pregunta_sin_responder
    # Regla determinista: si el último mensaje es del agente, no hay nada sin responder.
    if agent["wa_name"] and parsed.last_author and parsed.last_author.strip() == agent["wa_name"].strip():
        unanswered = False

    chat_id = db.add_chat(
        agent_id=user.id,
        customer=a.cliente,
        summary=a.resumen,
        status=a.estado,
        next_action=a.accion_siguiente,
        amount=a.monto,
        follow_up_at=follow_up,
        unanswered=unanswered,
    )
    row = db.get_chat(chat_id, user.id)
    await status_msg.edit_text(card_text(row), reply_markup=card_keyboard(chat_id))


async def on_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    doc = update.message.document
    if not (doc.file_name or "").lower().endswith(".txt"):
        await update.message.reply_text("Envíame el chat exportado de WhatsApp en formato .txt")
        return
    if doc.file_size and doc.file_size > 1_000_000:
        await update.message.reply_text("El archivo es muy grande (máximo 1 MB).")
        return
    f = await doc.get_file()
    data = bytes(await f.download_as_bytearray())
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    await _process(update, ctx, text)


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    text = update.message.text or ""
    if len(text) >= 150 or text.count("\n") >= 3:
        await _process(update, ctx, text)
    else:
        await update.message.reply_text(
            "Para analizar un chat envíame el archivo .txt o pega la conversación completa.\n/ayuda para ver los comandos."
        )


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _allowed(update):
        await q.answer()
        return
    db = _db(ctx)
    user_id = update.effective_user.id
    parts = q.data.split("|")
    action, chat_id = parts[0], int(parts[1])
    ok = False
    note = ""
    if action == "done":
        ok, note = db.mark_done(chat_id, user_id), "Hecho ✅"
    elif action == "snz":
        ok, note = db.snooze(chat_id, user_id, 60), "Te aviso en 1 hora ⏰"
    elif action == "st" and len(parts) == 3 and parts[2] in STATUSES:
        ok, note = db.set_status(chat_id, user_id, parts[2]), "Estado actualizado"
    await q.answer(note if ok else "No encontré ese chat")
    if ok:
        row = db.get_chat(chat_id, user_id)
        suffix = "\n\n✅ Cerrado" if row["done"] else ""
        keyboard = None if row["done"] else card_keyboard(chat_id)
        try:
            await q.edit_message_text(card_text(row) + suffix, reply_markup=keyboard)
        except Exception:
            log.debug("No se pudo editar el mensaje", exc_info=True)
