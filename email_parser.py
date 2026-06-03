"""Разбор письма Gmail API: заголовки, текст и данные уведомления Upwork."""
import base64
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

# Из ссылки на переписку оставляем только параметры, нужные для открытия
_KEEP_PARAMS = {"companyReference", "app_type"}

# Невидимые символы-распорки, которыми Upwork «раздувает» письма
_INVISIBLE = dict.fromkeys(
    [0x034F, 0x00AD, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0xFEFF, 0x2060],
    None,
)

# Прямые ссылки на переписку в Upwork выглядят так
_UPWORK_ROOM_PREFIX = "https://www.upwork.com/ab/messages/rooms/"


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


def clean_text(text: str) -> str:
    """Убирает невидимые символы и пустые строки."""
    text = text.translate(_INVISIBLE)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["style", "script", "head", "title"]):
        tag.decompose()
    return clean_text(soup.get_text("\n"))


def extract_body(payload: dict) -> str:
    """Возвращает читаемый текст письма. Сначала plain, потом html."""
    plain = _find_part(payload, "text/plain")
    if plain:
        return clean_text(plain)
    html = _find_part(payload, "text/html")
    if html:
        return html_to_text(html)
    return ""


def client_from_subject(subject: str) -> str:
    """Из темы «Aerogrip L. sent you a message» достаёт имя клиента."""
    for marker in (" sent you a message", " отправил", " — Upwork"):
        if marker in subject:
            return subject.split(marker)[0].strip()
    return subject.strip()


def _clean_link(href: str) -> str:
    """Убирает рекламные utm/braze-параметры, оставляя только нужные для входа."""
    parts = urlsplit(href)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k in _KEEP_PARAMS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def extract_upwork_info(payload: dict) -> dict:
    """Достаёт прямую ссылку на переписку и название проекта из письма Upwork."""
    info = {"link": "", "project": ""}
    html = _find_part(payload, "text/html")
    if not html:
        return info

    soup = BeautifulSoup(html, "html.parser")
    texts = []
    for anchor in soup.find_all("a"):
        href = anchor.get("href", "")
        if href.startswith(_UPWORK_ROOM_PREFIX):
            if not info["link"]:
                info["link"] = _clean_link(href)
            txt = " ".join(anchor.get_text().split())
            if txt:
                texts.append(txt)

    # Проект — самый длинный осмысленный текст среди ссылок на переписку
    for txt in sorted(texts, key=len, reverse=True):
        if len(txt) > 3:
            info["project"] = txt
            break
    return info
