"""Доступ к Gmail в режиме ТОЛЬКО ЧТЕНИЕ (scope gmail.readonly).

Важно: read-only означает, что скрипт ничего не помечает прочитанным,
не перемещает и не удаляет письма. Поэтому нативная почта на iPhone
продолжает работать как обычно — мы лишь читаем копии писем через API.
"""
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_service(credentials_file: str, token_file: str):
    """Возвращает авторизованный Gmail API клиент.

    При первом запуске откроет браузер для входа в Google и сохранит token.json.
    Дальше токен обновляется автоматически.
    """
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                raise SystemExit(
                    f"Не найден файл {credentials_file}. Скачай OAuth-credentials "
                    f"(тип 'Desktop app') из Google Cloud Console и положи рядом."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as fh:
            fh.write(creds.to_json())

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def build_query(sender: str, subject_query: str, lookback: str) -> str:
    """Собирает строку поиска в синтаксисе Gmail."""
    parts = []
    if sender:
        parts.append(f"from:{sender}")
    if subject_query:
        parts.append(subject_query)
    if lookback:
        parts.append(f"newer_than:{lookback}")
    return " ".join(parts)


def list_messages(service, query: str):
    """Список писем, подходящих под фильтр (новейшие первыми)."""
    resp = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=50)
        .execute()
    )
    return resp.get("messages", [])


def get_message(service, msg_id: str):
    """Полное письмо по id."""
    return (
        service.users()
        .messages()
        .get(userId="me", id=msg_id, format="full")
        .execute()
    )
