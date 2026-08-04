"""Upwork → Telegram.

Проверяет почту на новые письма от Upwork с уведомлением о сообщении клиента
и шлёт в Telegram-чат: кто написал, по какому проекту, сам текст и ссылку.

Использование:
    python main.py --auth        # один раз: авторизация в Google (token.json)
    python main.py               # одна проверка (удобно для cron)
    python main.py --loop        # бесконечный цикл (POLL_INTERVAL_SECONDS)
    python main.py --send-last N # тест: отправить последние N писем в чат
"""
import argparse
import html as html_lib
import sys
import time

import config
import gmail_client
import state as state_store
import telegram_client
from email_parser import (
    client_name,
    extract_interview_info,
    extract_invite_info,
    extract_message_text,
    extract_upwork_info,
    get_header,
    interview_title,
    invite_title,
    is_interview,
    is_invitation,
)

# Запасные ссылки, если в письме не нашлось прямой ссылки
FALLBACK_LINK = "https://www.upwork.com/nx/messages/"
FALLBACK_INVITE = "https://www.upwork.com/nx/find-work/"


def _esc(text: str) -> str:
    return html_lib.escape(text)


def format_message(client: str, project: str, message: str, link: str) -> str:
    lines = ["📩 <b>Новое сообщение в Upwork</b>", ""]
    lines.append(f"<b>От:</b> {_esc(client)}")
    if project and project != client:
        lines.append(f"<b>Проект:</b> {_esc(project)}")
    if message:
        lines.append("")
        lines.append(f"💬 {_esc(message)}")
    lines.append("")
    lines.append(f'🔗 <a href="{_esc(link or FALLBACK_LINK)}">Открыть переписку в Upwork</a>')
    return "\n".join(lines)


def format_interview(
    title: str, client: str, description: str, note: str, link: str
) -> str:
    lines = ["🎯 <b>Приглашение на интервью (Upwork)</b> #инвайт #интервью", ""]
    lines.append(f"<b>Вакансия:</b> {_esc(title)}")
    if client:
        lines.append(f"<b>Клиент:</b> {_esc(client)}")
    if note:
        lines.append("")
        lines.append(f"💬 <b>Сообщение клиента:</b> {_esc(note)}")
    if description:
        lines.append("")
        lines.append(_esc(description))
    lines.append("")
    lines.append(f'🔗 <a href="{_esc(link or FALLBACK_INVITE)}">Открыть приглашение</a>')
    return "\n".join(lines)


def format_invite(title: str, description: str, link: str) -> str:
    lines = ["📨 <b>Приглашение на проект (Upwork)</b> #инвайт", ""]
    lines.append(f"<b>Проект:</b> {_esc(title)}")
    if description:
        lines.append("")
        lines.append(_esc(description))
    lines.append("")
    lines.append(f'🔗 <a href="{_esc(link or FALLBACK_INVITE)}">Открыть приглашение</a>')
    return "\n".join(lines)


def _route(label: str) -> tuple:
    """Ищет клиента в CLIENT_ROUTES по имени. Возвращает (тег, chat_id) или ("", "")."""
    low = label.lower()
    for route in config.client_routes():
        if route["match"] in low:
            return route["tag"], route["chat_id"]
    return "", ""


def _build_message(full: dict) -> dict:
    """Из полного письма собирает всё, что нужно для отправки:

    label      — короткое имя для лога;
    subject    — тема письма;
    text       — готовый текст для Telegram;
    route_chat — chat_id рабочего чата проекта (или "");
    kind       — вид уведомления, он же тема форума:
                 invite — приглашения, client — письма известных клиентов
                 из CLIENT_ROUTES, message — остальные сообщения.

    Маршрутизация по клиентам применяется только к письмам с сообщениями:
    у приглашений «клиент» — это название вакансии, туда тег вешать нельзя.
    """
    subject = get_header(full, "Subject")
    payload = full.get("payload", {})

    if is_interview(subject):
        title = interview_title(subject)
        inv = extract_interview_info(payload, title)
        text = format_interview(
            title, inv["client"], inv["description"], inv["note"], inv["link"]
        )
        return {"label": title, "subject": subject, "text": text,
                "route_chat": "", "kind": "invite"}

    if is_invitation(subject):
        title = invite_title(subject)
        inv = extract_invite_info(payload)
        text = format_invite(title, inv["description"], inv["link"])
        return {"label": title, "subject": subject, "text": text,
                "route_chat": "", "kind": "invite"}

    client = client_name(get_header(full, "From"), subject)
    info = extract_upwork_info(payload, client)
    message = extract_message_text(payload, client)
    text = format_message(client, info["project"], message, info["link"])

    tag, route_chat = _route(client)
    if tag:
        text = f"🏷 #{_esc(tag)} — клиентское сообщение\n\n" + text
    return {"label": client, "subject": subject, "text": text,
            "route_chat": route_chat, "kind": "client" if tag else "message"}


def run_once() -> int:
    """Одна проверка почты. Возвращает количество пересланных писем."""
    service = gmail_client.get_service(config.CREDENTIALS_FILE, config.TOKEN_FILE)
    query = gmail_client.build_query(
        config.GMAIL_SENDER, config.GMAIL_SUBJECT_QUERY, config.GMAIL_LOOKBACK
    )
    print(f"[gmail] запрос: {query}")
    messages = gmail_client.list_messages(service, query)

    state = state_store.load(config.STATE_FILE)
    processed = set(state["processed"])

    token = config.telegram_bot_token()
    chat_id = config.telegram_chat_id()

    sent = 0
    # reversed → обрабатываем от старых к новым, чтобы порядок в чате был верный
    for ref in reversed(messages):
        msg_id = ref["id"]
        if msg_id in processed:
            continue

        try:
            full = gmail_client.get_message(service, msg_id)
            msg = _build_message(full)
            client, subject = msg["label"], msg["subject"]
            text, route_chat = msg["text"], msg["route_chat"]
            telegram_client.send_message(
                token, chat_id, text, thread_id=config.topic_for(msg["kind"])
            )
        except Exception as exc:  # noqa: BLE001 — одно битое письмо не рвёт заход
            print(f"[error] письмо {msg_id}: {exc}", file=sys.stderr)
            continue

        # Помечаем обработанным и сохраняем сразу: даже если следующее письмо
        # или копия в рабочий чат упадут, дубля в общем канале не будет.
        processed.add(msg_id)
        state["processed"].append(msg_id)
        state_store.save(config.STATE_FILE, state)
        sent += 1
        print(f"[tg] переслано: {client!r} — {subject!r}")

        if route_chat and route_chat != chat_id:
            try:
                telegram_client.send_message(token, route_chat, text)
                print(f"[tg] копия в рабочий чат {route_chat}")
            except Exception as exc:  # noqa: BLE001 — рабочий чат необязателен
                print(f"[warn] рабочий чат {route_chat} недоступен: {exc}", file=sys.stderr)

    print(f"[ok] новых писем переслано: {sent}")
    return sent


def send_last(count: int = 1) -> int:
    """Тест: берёт последние `count` писем Upwork (без ограничения по свежести)
    и шлёт их в чат с пометкой ТЕСТ. Помечает обработанными, чтобы штатный
    опрос не отправил их повторно."""
    service = gmail_client.get_service(config.CREDENTIALS_FILE, config.TOKEN_FILE)
    query = gmail_client.build_query(config.GMAIL_SENDER, config.GMAIL_SUBJECT_QUERY, "")
    print(f"[test] запрос (без newer_than): {query}")
    messages = gmail_client.list_messages(service, query)
    if not messages:
        print("[test] подходящих писем Upwork не найдено")
        return 0

    state = state_store.load(config.STATE_FILE)
    processed = set(state["processed"])
    token = config.telegram_bot_token()
    chat_id = config.telegram_chat_id()

    sent = 0
    # messages — новейшие первыми; reversed → в чат от старого к новому
    for ref in reversed(messages[:count]):
        msg_id = ref["id"]
        full = gmail_client.get_message(service, msg_id)
        msg = _build_message(full)
        client, subject = msg["label"], msg["subject"]
        text, route_chat = "🧪 <b>ТЕСТ</b>\n\n" + msg["text"], msg["route_chat"]
        telegram_client.send_message(
            token, chat_id, text, thread_id=config.topic_for(msg["kind"])
        )
        if route_chat and route_chat != chat_id:
            try:
                telegram_client.send_message(token, route_chat, text)
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] рабочий чат {route_chat} недоступен: {exc}", file=sys.stderr)

        if msg_id not in processed:
            processed.add(msg_id)
            state["processed"].append(msg_id)
        sent += 1
        print(f"[test] отправлено: {client!r} — {subject!r}")

    state_store.save(config.STATE_FILE, state)
    print(f"[ok] тест: отправлено {sent}")
    return sent


def main() -> None:
    parser = argparse.ArgumentParser(description="Upwork → Telegram пересылка")
    parser.add_argument(
        "--auth",
        action="store_true",
        help="Только авторизация в Google (создаёт token.json) и выход",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Бесконечный цикл с интервалом POLL_INTERVAL_SECONDS",
    )
    parser.add_argument(
        "--send-last",
        nargs="?",
        const=1,
        type=int,
        metavar="N",
        help="Тест: отправить последние N писем Upwork в чат (по умолчанию 1)",
    )
    args = parser.parse_args()

    if args.auth:
        gmail_client.get_service(config.CREDENTIALS_FILE, config.TOKEN_FILE)
        print("[ok] авторизация выполнена, token.json создан")
        return

    if args.send_last is not None:
        send_last(args.send_last)
        return

    if args.loop:
        print(f"[loop] старт, интервал {config.POLL_INTERVAL} c")
        while True:
            try:
                run_once()
            except Exception as exc:  # noqa: BLE001 — цикл не должен падать
                print(f"[error] {exc}", file=sys.stderr)
            time.sleep(config.POLL_INTERVAL)
    else:
        run_once()


if __name__ == "__main__":
    main()
