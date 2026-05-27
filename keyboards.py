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
    """Emoji + matn — ikonka yozuv yonida."""
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
    assignee_id = order.get("assigned_to_id")

    if status == "yangi":
        kb.button(text=_lbl("👷", "Men xizmat ko'rsataman"), callback_data=f"act:{order_id}:band")
        kb.button(text=_lbl("❌", "Rad etish"), callback_data=f"act:{order_id}:rad")
        kb.adjust(2)
    elif status == "jarayonda":
        if viewer_id is None or viewer_id == assignee_id:
            kb.button(text=_lbl("✔️", "Xizmat tugadi"), callback_data=f"act:{order_id}:tugadi")
        else:
            kb.button(
                text=_lbl("🔒", f"{order.get('assigned_to', 'Xodim')} xizmatda"),
                callback_data="noop",
            )
        kb.adjust(1)
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
