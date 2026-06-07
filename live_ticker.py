"""Guruh xabarlaridagi LIVE taymerni avtomatik yangilash (flood-safe)."""

from __future__ import annotations

import asyncio
import logging
import time

from aiogram import Bot

from config import settings
from keyboards import group_actions
from storage import any_live_orders, get_order, live_orders
from telegram_safe import flood_paused, run_telegram
from ui import order_card

log = logging.getLogger(__name__)

_last_edit_at: dict[int, float] = {}


def reset_edit_throttle() -> None:
    """Testlar uchun throttle holatini tozalash."""
    _last_edit_at.clear()


def _live_edit_interval() -> float:
    return float(settings().get("live_edit_sec", 20))


async def refresh_order_message(
    bot: Bot,
    group_id: int,
    order: dict,
    *,
    viewer_id: int | None = None,
    force: bool = False,
) -> bool:
    msg_id = order.get("group_message_id")
    if not msg_id:
        return False
    if flood_paused() and not force:
        return False

    fresh = get_order(order["id"]) or order
    if fresh["status"] not in ("yangi", "jarayonda"):
        _last_edit_at.pop(fresh["id"], None)
        return False

    now = time.monotonic()
    if not force:
        last = _last_edit_at.get(fresh["id"], 0.0)
        if now - last < _live_edit_interval():
            return False

    caption = order_card(fresh, for_group=True, live=True)
    markup = group_actions(fresh["id"], fresh, viewer_id)

    async def _edit() -> bool:
        await bot.edit_message_text(
            caption,
            chat_id=group_id,
            message_id=msg_id,
            parse_mode="HTML",
            reply_markup=markup,
        )
        return True

    ok = await run_telegram(_edit, label=f"edit #{fresh['id']}", force=force)
    if ok:
        _last_edit_at[fresh["id"]] = now
        return True
    if ok is None:
        _last_edit_at[fresh["id"]] = now
    return False


async def refresh_all_live(bot: Bot, group_id: int, *, force: bool = False) -> int:
    if flood_paused() and not force:
        return 0
    updated = 0
    for order in live_orders():
        if await refresh_order_message(bot, group_id, order, force=force):
            updated += 1
    return updated


class LiveTicker:
    def __init__(self, bot: Bot, group_id: int) -> None:
        self._bot = bot
        self._group_id = group_id
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self.stop()
        self._task = asyncio.create_task(self._loop())
        log.info(
            "LIVE taymer: tekshiruv har %ss, edit kamida %ss",
            settings()["tick_sec"],
            _live_edit_interval(),
        )

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    async def tick_once(self, *, force: bool = False) -> None:
        await refresh_all_live(self._bot, self._group_id, force=force)

    async def _loop(self) -> None:
        tick = settings()["tick_sec"]
        try:
            while True:
                if any_live_orders() and not flood_paused():
                    await refresh_all_live(self._bot, self._group_id)
                await asyncio.sleep(tick)
        except asyncio.CancelledError:
            pass
