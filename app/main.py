import logging

from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from app import config, handlers
from app.db import Database
from app.reminders import check_reminders


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # evita registrar el token en las URLs
    config.validate()

    application = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()
    application.bot_data["db"] = Database(config.DB_PATH)

    application.add_handler(CommandHandler(["start", "ayuda"], handlers.start))
    application.add_handler(CommandHandler("nombre", handlers.nombre))
    application.add_handler(CommandHandler("pendientes", handlers.pendientes))
    application.add_handler(CommandHandler("resumen", handlers.resumen))
    application.add_handler(CommandHandler("hecho", handlers.hecho))
    application.add_handler(MessageHandler(filters.Document.ALL, handlers.on_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text))
    application.add_handler(CallbackQueryHandler(handlers.on_button))

    application.job_queue.run_repeating(
        check_reminders, interval=config.REMINDER_INTERVAL_MIN * 60, first=30
    )
    logging.getLogger(__name__).info("Bot iniciado")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
