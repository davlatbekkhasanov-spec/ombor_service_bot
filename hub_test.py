"""Admin: hub test."""

from __future__ import annotations

from aiogram.types import Message

from config import is_admin
from yordamchi_push import push_to_yordamchi_hub

BTN_HUB_TEST = "🧪 Test (admin)"


async def handle_admin_hub_test(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not is_admin(uid):
        return await message.answer("Faqat admin uchun.")

    ok, via = await push_to_yordamchi_hub(
        tg_id=uid,
        bot_key="ombor",
        summary="[TEST] #99 Xizmat: bajarildi, 12 daqiqa",
    )
    await message.answer(
        f"{'✅' if ok else '❌'} Ombor → yordamchi hub ({via})\n"
        "Endi davlat-yordamchi botda ✅ Якунлаш yuboring."
    )
