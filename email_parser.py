"""Разбор письма Gmail API: заголовки и текст из HTML/plain."""
import base64

from bs4 import BeautifulSoup


def get_header(message: dict, name: str) -> str:
    for header in message.get("payload", {}).get("headers", []):
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")


def _find_part(payload: dict, mime: str):
    """Рекурсивно ищет первую часть нужного MIME-типа с непустым телом."""
    if payload.get("mimeType") == mime and payload.get("body", {}).get("data"):
        return _decode(payload["body"]["data"])
    for part in payload.get("parts", []) or []:
        found = _find_part(part, mime)
        if found:
            return found
    return None


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["style", "script", "head", "title"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [line.strip() for line in text.splitlines()]
    # Убираем пустые строки и схлопываем повторы
    cleaned = []
    for line in lines:
        if line:
            cleaned.append(line)
    return "\n".join(cleaned)


def extract_body(payload: dict) -> str:
    """Возвращает читаемый текст письма. Сначала plain, потом html."""
    plain = _find_part(payload, "text/plain")
    if plain:
        return plain.strip()
    html = _find_part(payload, "text/html")
    if html:
        return html_to_text(html)
    return ""
