"""Разбор письма Gmail API: заголовки, текст и данные уведомления Upwork."""
import base64
import re
from email.utils import parseaddr
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

# Инициалы-аватарка вроде «IR», «AL»
_INITIALS = re.compile(r"^[A-Z]{1,4}$")

# Служебные подписи ссылок/ячеек, которые не являются текстом сообщения
_STOP_LABELS = {
    "reply",
    "view on upwork",
    "view your message",
    "view your message and send a reply.",
    "find work",
    "release notes",
}

# Максимум символов текста сообщения
_MSG_LIMIT = 1500


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


def client_name(from_header: str, subject: str = "") -> str:
    """Имя клиента: из поля «От» (`Ivan R. via Upwork` → `Ivan R.`)."""
    name = parseaddr(from_header)[0]
    name = name.replace(" via Upwork", "").strip()
    if name:
        return name
    # запасной вариант — из темы «X sent you a message»
    for marker in (" sent you a message", " отправил"):
        if marker in subject:
            return subject.split(marker)[0].strip()
    return subject.strip()


def _leaf_cells(soup) -> list:
    """Текст «листовых» ячеек таблицы письма в порядке следования."""
    cells = []
    for el in soup.find_all("td"):
        if el.find("td"):  # есть вложенные td — не лист
            continue
        txt = " ".join(el.get_text(" ", strip=True).split())
        txt = txt.translate(_INVISIBLE).strip()
        if txt:
            cells.append(txt)
    return cells


def _is_boundary(text: str, client: str) -> bool:
    low = text.lower().strip()
    if _INITIALS.match(text.strip()):
        return True
    if client and text.strip() == client.strip():
        return True
    if "utc" in low and any(ch.isdigit() for ch in text):
        return True
    if low in _STOP_LABELS:
        return True
    return False


def extract_message_text(payload: dict, client: str = "") -> str:
    """Достаёт сам текст сообщения клиента (тип письма «X sent you a message»).

    Сообщение лежит в ячейке(ах) перед ссылкой «View on Upwork».
    Для писем-приглашений («direct message from a client») текста нет → "".
    """
    html = _find_part(payload, "text/html")
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["style", "script", "head", "title"]):
        tag.decompose()

    cells = _leaf_cells(soup)
    anchor = None
    for i, txt in enumerate(cells):
        if "view on upwork" in txt.lower():
            anchor = i  # берём последнее вхождение
    if anchor is None:
        return ""

    collected = []
    for txt in reversed(cells[:anchor]):
        if _is_boundary(txt, client):
            break
        collected.append(txt)
    collected.reverse()
    return "\n".join(collected)[:_MSG_LIMIT].strip()


def _clean_link(href: str) -> str:
    """Убирает рекламные utm/braze-параметры, оставляя только нужные для входа."""
    parts = urlsplit(href)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k in _KEEP_PARAMS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def extract_upwork_info(payload: dict, client: str = "") -> dict:
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

    # Проект — самый длинный осмысленный текст среди ссылок (не имя, не инициалы,
    # не служебная подпись вроде «Reply»/«View on Upwork»)
    for txt in sorted(texts, key=len, reverse=True):
        low = txt.lower()
        if len(txt) <= 3 or _INITIALS.match(txt) or low in _STOP_LABELS:
            continue
        if client and txt.strip() == client.strip():
            continue
        info["project"] = txt
        break
    return info
