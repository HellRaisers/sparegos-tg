"""Отправка сообщений в Telegram через Bot API (без лишних зависимостей)."""
import re

import requests

API_URL = "https://api.telegram.org/bot{token}/sendMessage"
# Лимит Telegram — 4096 символов. Берём с запасом.
MAX_LEN = 4000

_TAG_RE = re.compile(r"<[^>]+>")


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i : i + size]


def _post(url: str, chat_id: str, text: str, parse_mode) -> None:
    data = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if parse_mode:
        data["parse_mode"] = parse_mode
    resp = requests.post(url, data=data, timeout=30)
    resp.raise_for_status()


def send_message(token: str, chat_id: str, text: str, parse_mode: str = "HTML") -> None:
    """Шлёт текст в чат. Длинные сообщения режутся на части.

    Если нарезка разорвала HTML-тег, Telegram отвечает 400 «can't parse entities».
    В этом случае шлём тот же кусок простым текстом: уведомление важнее разметки,
    иначе письмо не будет отправлено никогда и повиснет в вечных повторах.
    """
    url = API_URL.format(token=token)
    for chunk in _chunks(text, MAX_LEN):
        try:
            _post(url, chat_id, chunk, parse_mode)
        except requests.HTTPError as exc:
            resp = exc.response
            if not (parse_mode and resp is not None and resp.status_code == 400
                    and "parse" in resp.text.lower()):
                raise
            _post(url, chat_id, _TAG_RE.sub("", chunk), None)
