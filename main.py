"""Upwork → Telegram.

Проверяет почту на новые письма от Upwork с уведомлением о сообщении клиента
и пересылает их содержимое в Telegram-чат.

Использование:
    python main.py --auth     # один раз: авторизация в Google (создаёт token.json)
    python main.py            # одна проверка (удобно для cron каждые 10 минут)
    python main.py --loop     # бесконечный цикл с интервалом POLL_INTERVAL_SECONDS
"""
import argparse
import html as html_lib
import sys
import time

import config
import gmail_client
import state as state_store
import telegram_client
from email_parser import extract_body, get_header

# Сколько символов тела письма максимум отправлять
BODY_LIMIT = 3500


def format_message(sender: str, subject: str, date: str, body: str) -> str:
    body = body[:BODY_LIMIT]
    if len(body) == BODY_LIMIT:
        body += "\n…"
    return (
        "📩 <b>Новое сообщение из Upwork</b>\n\n"
        f"<b>От:</b> {html_lib.escape(sender)}\n"
        f"<b>Тема:</b> {html_lib.escape(subject)}\n"
        f"<b>Дата:</b> {html_lib.escape(date)}\n\n"
        f"{html_lib.escape(body)}"
    )


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

        full = gmail_client.get_message(service, msg_id)
        sender = get_header(full, "From")
        subject = get_header(full, "Subject")
        date = get_header(full, "Date")
        body = extract_body(full.get("payload", {})) or full.get("snippet", "")

        text = format_message(sender, subject, date, body)
        telegram_client.send_message(token, chat_id, text)

        processed.add(msg_id)
        state["processed"].append(msg_id)
        sent += 1
        print(f"[tg] переслано: {subject!r}")

    state_store.save(config.STATE_FILE, state)
    print(f"[ok] новых писем переслано: {sent}")
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
    args = parser.parse_args()

    if args.auth:
        gmail_client.get_service(config.CREDENTIALS_FILE, config.TOKEN_FILE)
        print("[ok] авторизация выполнена, token.json создан")
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
