"""Telegram flood limit — kutish va qayta urinish."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, TypeVar

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

log = logging.getLogger(__name__)

T = TypeVar("T")

_flood_until: float = 0.0


def flood_paused() -> bool:
    return time.monotonic() < _flood_until


def pause_for_flood(seconds: float) -> None:
    global _flood_until
    _flood_until = max(_flood_until, time.monotonic() + max(0.0, seconds))


def reset_flood_state() -> None:
    """Testlar uchun flood holatini tozalash."""
    global _flood_until
    _flood_until = 0.0


async def run_telegram(
    action: Callable[[], Awaitable[T]],
    *,
    label: str = "",
    force: bool = False,
) -> T | None:
    """RetryAfter bo'lsa kutadi; BadRequest 'not modified' — None."""
    if flood_paused() and not force:
        return None
    if flood_paused() and force:
        wait = _flood_until - time.monotonic()
        if wait > 0:
            log.info("Flood %s — force kutish %.1fs", label or "telegram", wait)
            await asyncio.sleep(wait)
    try:
        return await action()
    except TelegramRetryAfter as e:
        pause_for_flood(float(e.retry_after))
        log.warning("Flood %s — %ss kutamiz", label or "telegram", e.retry_after)
        await asyncio.sleep(float(e.retry_after))
        try:
            return await action()
        except TelegramRetryAfter:
            return None
        except TelegramBadRequest as err:
            if "message is not modified" in str(err).lower():
                return None
            raise
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return None
        raise
