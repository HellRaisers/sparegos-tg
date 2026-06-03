"""Хранение id уже обработанных писем, чтобы не слать дубли.

Нужно потому, что доступ к почте read-only — мы не можем пометить письмо
как прочитанное, поэтому ведём свой список обработанных id.
"""
import json
import os

MAX_KEEP = 1000


def load(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r") as fh:
            try:
                return json.load(fh)
            except json.JSONDecodeError:
                pass
    return {"processed": []}


def save(path: str, state: dict) -> None:
    # Ограничиваем размер истории, чтобы файл не рос бесконечно.
    state["processed"] = state["processed"][-MAX_KEEP:]
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh, ensure_ascii=False)
    os.replace(tmp, path)
