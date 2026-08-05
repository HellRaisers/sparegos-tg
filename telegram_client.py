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
        body = resp.json()
    except ValueError:
        return ""
    params = body.get("parameters") if isinstance(body, dict) else None
    if not isinstance(params, dict):
        return ""
    return str(params.get("migrate_to_chat_id") or "")


def _send_chunk(url: str, chat_id: str, chunk: str, parse_mode, thread_id: str) -> tuple:
    """Отправляет один кусок, по очереди снимая устранимые причины отказа.

    Каждая попытка убирает ровно одну помеху, поэтому и комбинации (например
    миграция чата, а следом разорванный тег) отрабатываются. Возвращает
    (chat_id, thread_id) — возможно изменённые, чтобы следующие куски шли
    сразу правильно и не собирали те же ошибки заново.
    """
    for _ in range(4):
        try:
            _post(url, chat_id, chunk, parse_mode, thread_id)
            return chat_id, thread_id
        except requests.HTTPError as exc:
            resp = exc.response
            if resp is None or resp.status_code != 400:
                raise
            desc = resp.text.lower()

            new_chat_id = _migrated_chat_id(resp)
            if new_chat_id and new_chat_id != chat_id:
                print(
                    f"[warn] чат {chat_id} стал супергруппой, новый id {new_chat_id} — "
                    f"пропиши его в TELEGRAM_CHAT_ID",
                    file=sys.stderr,
                )
                chat_id = new_chat_id
                continue

            if thread_id and ("thread" in desc or "topic" in desc):
                print(
                    f"[warn] тема {thread_id} в чате {chat_id} недоступна "
                    f"({resp.text.strip()[:120]}) — шлю в общую ленту, проверь TOPIC_*",
                    file=sys.stderr,
                )
                thread_id = ""
                continue

            if parse_mode and "parse" in desc:
                chunk, parse_mode = _TAG_RE.sub("", chunk), None
                continue

            raise
    raise RuntimeError(f"не удалось отправить сообщение в чат {chat_id}")


def send_message(
    token: str, chat_id: str, text: str, parse_mode: str = "HTML", thread_id: str = ""
) -> None:
    """Шлёт текст в чат (при указании thread_id — в конкретную тему форума).
    Длинные сообщения режутся на части.

    Три случая, из-за которых уведомление иначе не дошло бы никогда:
    - группу превратили в супергруппу → её id сменился, Telegram возвращает
      новый в migrate_to_chat_id; шлём туда и просим обновить TELEGRAM_CHAT_ID;
    - тема удалена, закрыта или id неверный → шлём в общую ленту чата:
      уведомление не в той теме лучше, чем отсутствие уведомления;
    - нарезка разорвала HTML-тег → Telegram отвечает 400 «can't parse entities»,
      шлём тот же кусок простым текстом: уведомление важнее разметки.
    """
    url = API_URL.format(token=token)
    for chunk in _chunks(text, MAX_LEN):
        chat_id, thread_id = _send_chunk(url, chat_id, chunk, parse_mode, thread_id)
