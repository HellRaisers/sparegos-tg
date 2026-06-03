"""Отправка сообщений в Telegram через Bot API (без лишних зависимостей)."""
import requests

API_URL = "https://api.telegram.org/bot{token}/sendMessage"
# Лимит Telegram — 4096 символов. Берём с запасом.
MAX_LEN = 4000


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i : i + size]


def send_message(token: str, chat_id: str, text: str, parse_mode: str = "HTML") -> None:
    """Шлёт текст в чат. Длинные сообщения режутся на части."""
    url = API_URL.format(token=token)
    for chunk in _chunks(text, MAX_LEN):
        resp = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=30,
        )
        resp.raise_for_status()
