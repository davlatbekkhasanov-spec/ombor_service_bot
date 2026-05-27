"""Muhit o'zgaruvchilari."""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _parse_int(raw: str | None) -> int | None:
    raw = (raw or "").strip().strip('"').strip("'")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_ids(raw: str | None) -> frozenset[int]:
    out: set[int] = set()
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return frozenset(out)


@lru_cache
def settings() -> dict:
    return {
        "bot_token": os.getenv("BOT_TOKEN", ""),
        "group_id": _parse_int(os.getenv("GROUP_ID")),
        "admin_ids": _parse_ids(os.getenv("ADMIN_IDS")),
    }


def is_admin(user_id: int | None) -> bool:
    if user_id is None:
        return False
    admins = settings()["admin_ids"]
    if not admins:
        return True
    return user_id in admins
