import logging

from telegram.ext import ContextTypes

from app import config
from app.handlers import card_keyboard, card_text

log = logging.getLogger(__name__)


async def check_reminders(ctx: ContextTypes.DEFAULT_TYPE):
    db = ctx.application.bot_data["db"]
    for row in db.due_reminders(config.REMINDER_COOLDOWN_MIN):
        try:
            await ctx.bot.send_message(
                chat_id=row["agent_id"],
                text="🔔 Recordatorio\n\n" + card_text(row),
                reply_markup=card_keyboard(row["id"], reminder=True),
            )
        except Exception:
            log.exception("No se pudo enviar el recordatorio del chat %s", row["id"])
        # Se marca igual para no insistir cada ciclo si Telegram rechaza el envío.
        db.mark_reminded(row["id"])
