"""Отправка сообщений в Telegram через Bot API (без лишних зависимостей)."""
import re
import sys

import requests

API_URL = "https://api.telegram.org/bot{token}/sendMessage"
# Лимит Telegram — 4096 символов. Берём с запасом.
MAX_LEN = 4000

_TAG_RE = re.compile(r"<[^>]+>")


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i : i + size]


def _post(url: str, chat_id: str, text: str, parse_mode, thread_id: str = "") -> None:
    data = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if parse_mode:
        data["parse_mode"] = parse_mode
    if thread_id:
        data["message_thread_id"] = thread_id
    resp = requests.post(url, data=data, timeout=30)
    resp.raise_for_status()


def _migrated_chat_id(resp) -> str:
    """Новый id чата, если группу превратили в супергруппу (иначе "")."""
    try:
        params = resp.json().get("parameters") or {}
    except ValueError:
        return ""
    return str(params.get("migrate_to_chat_id") or "")


def send_message(
    token: str, chat_id: str, text: str, parse_mode: str = "HTML", thread_id: str = ""
) -> None:
    """Шлёт текст в чат (при указании thread_id — в конкретную тему форума).
    Длинные сообщения режутся на части.

    Два случая, из-за которых уведомление иначе не дошло бы никогда:
    - нарезка разорвала HTML-тег → Telegram отвечает 400 «can't parse entities»,
      шлём тот же кусок простым текстом: уведомление важнее разметки;
    - группу превратили в супергруппу → её id сменился, Telegram возвращает
      новый в migrate_to_chat_id; отправляем туда и громко пишем в лог, чтобы
      обновить TELEGRAM_CHAT_ID в .env.
    """
    url = API_URL.format(token=token)
    for chunk in _chunks(text, MAX_LEN):
        try:
            _post(url, chat_id, chunk, parse_mode, thread_id)
            continue
        except requests.HTTPError as exc:
            resp = exc.response
            if resp is None or resp.status_code != 400:
                raise
            new_chat_id = _migrated_chat_id(resp)
            if new_chat_id:
                print(
                    f"[warn] чат {chat_id} стал супергруппой, новый id {new_chat_id} — "
                    f"пропиши его в TELEGRAM_CHAT_ID",
                    file=sys.stderr,
                )
                _post(url, new_chat_id, chunk, parse_mode, thread_id)
                continue
            if not (parse_mode and "parse" in resp.text.lower()):
                raise
            _post(url, chat_id, _TAG_RE.sub("", chunk), None, thread_id)
