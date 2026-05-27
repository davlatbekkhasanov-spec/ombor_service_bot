"""Guruh xabarlaridagi LIVE taymerni avtomatik yangilash."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from config import settings
from keyboards import group_actions
from storage import any_live_orders, get_order, live_orders
from ui import order_card

log = logging.getLogger(__name__)


async def refresh_order_message(bot: Bot, group_id: int, order: dict) -> bool:
    msg_id = order.get("group_message_id")
    if not msg_id:
        return False
    fresh = get_order(order["id"]) or order
    if fresh["status"] not in ("yangi", "jarayonda"):
        return False
    try:
        await bot.edit_message_text(
            order_card(fresh, for_group=True, live=True),
            chat_id=group_id,
            message_id=msg_id,
            parse_mode="HTML",
            reply_markup=group_actions(fresh["id"], fresh),
        )
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return False
        log.warning("Taymer yangilash #%s: %s", order["id"], e)
        return False
    except Exception:
        log.exception("Taymer yangilash xato #%s", order["id"])
        return False


async def refresh_all_live(bot: Bot, group_id: int) -> int:
    updated = 0
    for order in live_orders():
        if await refresh_order_message(bot, group_id, order):
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
        log.info("LIVE taymer ishga tushdi (har %ss)", settings()["tick_sec"])

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    async def tick_once(self) -> None:
        await refresh_all_live(self._bot, self._group_id)

    async def _loop(self) -> None:
        tick = settings()["tick_sec"]
        try:
            while True:
                if any_live_orders():
                    await refresh_all_live(self._bot, self._group_id)
                await asyncio.sleep(tick)
        except asyncio.CancelledError:
            pass
