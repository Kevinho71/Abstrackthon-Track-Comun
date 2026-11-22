import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
DB_PATH = os.getenv("DB_PATH", "./data/app.db")
TZ_NAME = os.getenv("TZ", "UTC")
REMINDER_INTERVAL_MIN = int(os.getenv("REMINDER_INTERVAL_MIN", "15"))
REMINDER_COOLDOWN_MIN = int(os.getenv("REMINDER_COOLDOWN_MIN", "120"))
MAX_TRANSCRIPT_CHARS = 24000

ALLOWED_USER_IDS = [
    int(x) for x in os.getenv("ALLOWED_USER_IDS", "").replace(" ", "").split(",") if x
]

try:
    LOCAL_TZ = ZoneInfo(TZ_NAME)
except Exception:
    LOCAL_TZ = ZoneInfo("UTC")


def validate() -> None:
    missing = [
        n
        for n, v in (
            ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
            ("GEMINI_API_KEY", GEMINI_API_KEY),
        )
        if not v
    ]
    if missing:
        raise RuntimeError("Faltan variables de entorno: " + ", ".join(missing))
