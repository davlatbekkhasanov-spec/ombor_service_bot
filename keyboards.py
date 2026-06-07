"""Tugmalar."""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from storage import STATUSES
from ui import format_duration

REQUEST_TYPES = {
    "call_staff": ("🙋 Xizmat so'rovi", "Xizmat"),
    "check_client": ("👀 Mijozga qarang", "Mijoz"),
    "product_order": ("📦 Tovar buyurtma", "Buyurtma"),
    "info": ("ℹ️ Savol", "Savol"),
}

INSTANT_TYPES = frozenset({"call_staff", "check_client"})


def _lbl(icon: str, text: str) -> str:
    return f"{icon}  {text}"


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=_lbl("🙋", "Xizmat ko'rsating"), callback_data="req:call_staff")
    kb.button(text=_lbl("👀", "Mijozga qarang"), callback_data="req:check_client")
    kb.button(text=_lbl("📦", "Tovar buyurtma"), callback_data="req:product_order")
    kb.button(text=_lbl("ℹ️", "Savol"), callback_data="req:info")
    kb.adjust(2, 1)
    return kb.as_markup()


def back_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=_lbl("◀️", "Asosiy menyu"), callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def group_actions(order_id: int, order: dict, viewer_id: int | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    status = order["status"]
    staff_ids = order.get("staff_ids") or set()

    if status == "yangi":
        kb.button(text=_lbl("👷", "Men xizmat ko'rsataman"), callback_data=f"act:{order_id}:band")
        kb.button(text=_lbl("❌", "Rad etish"), callback_data=f"act:{order_id}:rad")
        kb.adjust(2)
    elif status == "jarayonda":
        on_team = viewer_id is not None and viewer_id in staff_ids
        if on_team:
            kb.button(text=_lbl("✔️", "Xizmat tugadi"), callback_data=f"act:{order_id}:tugadi")
            kb.adjust(1)
        else:
            # Guruhda klaviatura hammaga bir xil — jamoa tugatishi uchun ikkalasi ham kerak
            kb.button(text=_lbl("➕", "Qo'shilaman"), callback_data=f"act:{order_id}:qoshil")
            kb.button(text=_lbl("✔️", "Xizmat tugadi"), callback_data=f"act:{order_id}:tugadi")
            kb.adjust(2)
    else:
        label = STATUSES.get(status, status)
        if status == "bajarildi":
            label = _lbl("✔️", format_duration(order))
        kb.button(text=label, callback_data="noop")
        kb.adjust(1)
    return kb.as_markup()


def report_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=_lbl("📊", "Bugun"), callback_data="report:today")
    kb.button(text=_lbl("👷", "Xodimlar"), callback_data="report:staff")
    kb.button(text=_lbl("📈", "Umumiy"), callback_data="report:all")
    kb.adjust(3)
    return kb.as_markup()
