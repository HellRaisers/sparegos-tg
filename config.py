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
    'subject:("sent you a message" OR "direct message from a client" '
    'OR "Invitation to Apply" OR "Invitation to Interview")',
)
GMAIL_LOOKBACK = os.getenv("GMAIL_LOOKBACK", "2d")

# ── Маршрутизация по клиентам ──────────────────────────────
# Формат: Имя=Тег[:chat_id];Имя=Тег[:chat_id]
# «Имя» ищется в имени отправителя письма без учёта регистра. «Тег» попадает
# в уведомление хештегом (#HillTribe) — так ПМ видит, что это клиентское
# сообщение и по какому проекту. Если указан chat_id — копия уведомления
# дополнительно уходит в этот рабочий чат (бот должен быть туда добавлен).
CLIENT_ROUTES = os.getenv("CLIENT_ROUTES", "Peng=HillTribe;Liad=Truedose")


def client_routes() -> list:
    """Разбирает CLIENT_ROUTES в список {"match", "tag", "chat_id"}."""
    routes = []
    for item in CLIENT_ROUTES.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        name, rest = item.split("=", 1)
        tag, _, chat = rest.partition(":")
        if name.strip() and tag.strip():
            routes.append(
                {"match": name.strip().lower(), "tag": tag.strip(), "chat_id": chat.strip()}
            )
    return routes


# ── Темы (форум) в основном чате ───────────────────────────
# id темы (message_thread_id) для каждого вида уведомлений. Работает только
# если основной чат — супергруппа с включёнными темами. Если не задано,
# уведомление уходит в общую ленту чата, как раньше.
TOPIC_IDS = {
    "client": os.getenv("TOPIC_CLIENTS", ""),
    "invite": os.getenv("TOPIC_INVITES", ""),
    "message": os.getenv("TOPIC_MESSAGES", ""),
}


def topic_for(kind: str) -> str:
    """id темы для вида уведомления: client / invite / message."""
    return (TOPIC_IDS.get(kind) or "").strip()


# ── Прочее ─────────────────────────────────────────────────
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "600"))

CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", "token.json")
STATE_FILE = os.getenv("STATE_FILE", "state.json")
