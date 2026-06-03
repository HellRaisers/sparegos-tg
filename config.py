"""Конфигурация приложения. Значения берутся из переменных окружения / .env."""
import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(
            f"Не задана обязательная переменная окружения {name}. "
            f"Скопируй .env.example в .env и заполни значения."
        )
    return value


# ── Telegram ───────────────────────────────────────────────
def telegram_bot_token() -> str:
    return _require("TELEGRAM_BOT_TOKEN")


def telegram_chat_id() -> str:
    return _require("TELEGRAM_CHAT_ID")


# ── Фильтр писем (синтаксис поиска Gmail) ──────────────────
GMAIL_SENDER = os.getenv("GMAIL_SENDER", "upwork.com")
GMAIL_SUBJECT_QUERY = os.getenv(
    "GMAIL_SUBJECT_QUERY",
    'subject:("new message" OR "sent you a message" OR "новое сообщение")',
)
GMAIL_LOOKBACK = os.getenv("GMAIL_LOOKBACK", "2d")

# ── Прочее ─────────────────────────────────────────────────
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "600"))

CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", "token.json")
STATE_FILE = os.getenv("STATE_FILE", "state.json")
