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

# Ссылка на отклик/вакансию в письме-приглашении
_PROPOSAL_MARKER = "/nx/proposals/"
# Максимум символов описания вакансии в приглашении
_DESC_LIMIT = 800

# ── Письма «Invitation to Interview» (отправитель upwork@t.upwork.com) ──
# Вступительная строка перед названием вакансии
_INTERVIEW_INTRO = "a client invited you to a job"
# Подпись перед личным сообщением клиента
_INTERVIEW_NOTE_LABEL = "personal note from client"
# Текст ссылки на приглашение
_INTERVIEW_LINK_TEXT = "view invite"
# Ячейки, на которых блок приглашения заканчивается
_INTERVIEW_STOP = {"view invite", "decline", "mobile app", "follow us"}
# Условия работы: «Hourly • More than 6 months», «Fixed-price • $250 • 1 to 3 months»
_TERMS_RE = re.compile(r"^(hourly|fixed[\s-]?price)\b", re.I)
# Upwork обрезает описание и вешает ссылку «more» — убираем этот хвост
_MORE_TAIL_RE = re.compile(r"\s*(\.\.\.|…)\s*more\s*$", re.I)
# Шапка и подвал письма — если не нашлось вступление, они не должны попасть в описание
_CHROME_MARKERS = ("find work", "privacy policy", "follow us", "© 2015", "lytton ave")
# Шаблонный текст приглашения — не является личным сообщением клиента
_NOTE_BOILER_RE = re.compile(
    r"(hello!?\s*)?i'?d like to invite you to take a look at the job i'?ve posted\.?"
    r"|please submit a proposal if you'?re available and interested\.?",
    re.I,
)
# Подпись клиента в конце заметки: «Kyle P.», «Vostock M.»
_CLIENT_SIGN_RE = re.compile(r"(?:^|\s)(\S+\s+[A-Z]\.)\s*$")


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


def _strip_query(href: str) -> str:
    parts = urlsplit(href)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def is_invitation(subject: str) -> bool:
    """Письмо-приглашение «Invitation to Apply for: …»."""
    return subject.strip().lower().startswith("invitation to apply")


def invite_title(subject: str) -> str:
    """Название вакансии из темы приглашения."""
    s = subject.strip()
    marker = "invitation to apply for:"
    if s.lower().startswith(marker):
        return s[len(marker):].strip()
    return s


def is_interview(subject: str) -> bool:
    """Письмо-приглашение на интервью «Invitation to Interview for: …»."""
    return subject.strip().lower().startswith("invitation to interview")


def interview_title(subject: str) -> str:
    """Название вакансии из темы приглашения на интервью."""
    s = subject.strip()
    marker = "invitation to interview for:"
    if s.lower().startswith(marker):
        return s[len(marker):].strip()
    return s


def _interview_note(soup) -> tuple:
    """Текст после подписи «Personal note from client» → (заметка, имя клиента).

    Ячейку с заметкой нельзя взять через _leaf_cells: внутри неё лежит вложенная
    пустая td-распорка, из-за которой ячейка не считается листовой. Поэтому идём
    по документу от самой подписи.
    """
    label = soup.find(string=lambda s: s and _INTERVIEW_NOTE_LABEL in s.lower())
    cell = label.find_parent("td") if label else None
    if cell is None:
        return "", ""

    text = ""
    for nxt in cell.find_all_next("td"):
        candidate = " ".join(nxt.get_text(" ", strip=True).split())
        candidate = candidate.translate(_INVISIBLE).strip()
        if not candidate or candidate.lower() in _INTERVIEW_STOP:
            continue
        text = candidate
        break
    if not text:
        return "", ""

    client = ""
    match = _CLIENT_SIGN_RE.search(text)
    if match:
        client = match.group(1)
        text = text[: match.start()].strip()

    note = " ".join(_NOTE_BOILER_RE.sub(" ", text).split()).strip()
    return note[:_DESC_LIMIT], client


def extract_interview_info(payload: dict, title: str = "") -> dict:
    """Из письма «Invitation to Interview» достаёт условия, описание вакансии,
    имя клиента, его личное сообщение и ссылку на приглашение.

    Ссылки в таких письмах завёрнуты в трекинг-редирект link.t.upwork.com,
    поэтому берём href у кнопки «View invite» как есть — он рабочий.
    """
    info = {"link": "", "terms": "", "description": "", "note": "", "client": ""}
    html = _find_part(payload, "text/html")
    if not html:
        return info
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["style", "script", "head", "title"]):
        tag.decompose()

    for anchor in soup.find_all("a"):
        text = " ".join(anchor.get_text().split()).lower()
        href = anchor.get("href", "")
        if text == _INTERVIEW_LINK_TEXT and href:
            info["link"] = href
            break
    if not info["link"] and title:
        # запасной вариант — ссылка с названием вакансии
        for anchor in soup.find_all("a"):
            if " ".join(anchor.get_text().split()) == title and anchor.get("href"):
                info["link"] = anchor["href"]
                break

    cells = _leaf_cells(soup)
    start = 0
    for i, cell in enumerate(cells):
        if cell.lower().startswith(_INTERVIEW_INTRO):
            start = i + 1
            break

    body = []
    for cell in cells[start:]:
        low = cell.lower()
        if low in _INTERVIEW_STOP or low.startswith("download the upwork app"):
            break
        if low.startswith(_INTERVIEW_NOTE_LABEL):
            continue  # заметку берём отдельно, см. _interview_note
        if title and cell.strip() == title.strip():
            continue  # название уже взяли из темы
        if any(marker in low for marker in _CHROME_MARKERS):
            continue  # шапка/подвал письма
        body.append(cell)

    for cell in list(body):
        # условия — это короткая строка вида «Hourly • More than 6 months»
        if _TERMS_RE.match(cell) or ("•" in cell and len(cell) <= 80):
            info["terms"] = cell
            body.remove(cell)
            break

    if body:
        longest = max(body, key=len)
        info["description"] = _MORE_TAIL_RE.sub("…", longest)[:_DESC_LIMIT].strip()
    info["note"], info["client"] = _interview_note(soup)
    return info


def extract_invite_info(payload: dict) -> dict:
    """Из письма-приглашения достаёт описание вакансии, условия и ссылку на отклик."""
    info = {"link": "", "description": "", "budget": ""}
    html = _find_part(payload, "text/html")
    if not html:
        return info
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["style", "script", "head", "title"]):
        tag.decompose()

    for anchor in soup.find_all("a"):
        href = anchor.get("href", "")
        if _PROPOSAL_MARKER in href:
            info["link"] = _strip_query(href)
            break

    cells = _leaf_cells(soup)
    # Описание идёт после строки-приглашения и до блока «Payment Type»/«Submit Proposal»
    start = 0
    for i, cell in enumerate(cells):
        low = cell.lower()
        if "take a look at the job" in low or "invited to submit a proposal" in low:
            start = i + 1

    boiler = (
        "read more about the job",
        "invited to submit a proposal",
        "i'd like to invite you",
        "take a look at the job",
        "please submit a proposal",
    )
    desc = []
    for cell in cells[start:]:
        low = cell.lower()
        if low.startswith("payment type"):
            budget = " ".join(cell.split())
            for kw in ("Estimated Time", "Estimated Budget", "Time Commitment"):
                budget = budget.replace(kw, "· " + kw)
            info["budget"] = budget
            break
        if low in ("submit proposal", "decline") or "know someone for the job" in low:
            break
        if any(b in low for b in boiler):
            continue
        desc.append(cell)
    text = _MORE_TAIL_RE.sub("…", "\n".join(desc))
    info["description"] = text[:_DESC_LIMIT].strip()
    return info


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
