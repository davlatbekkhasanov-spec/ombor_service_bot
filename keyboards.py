"""Tugmalar."""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from storage import STATUSES
from ui import format_duration

REQUEST_TYPES = {
    "call_staff": ("🙋 Xizmat so'rovi", "Xizmat"),
    "check_client": ("👀 Mijozga qarang", "Mijoz"),
    "product_order": ("📦 Tovar buyurtma", "Buyurtma"),
    "bring_product": ("📋 Mahsulot olib keling", "Olib kelish"),
    "vip": ("⭐ VIP / Shoshilinch", "VIP"),
    "complaint": ("⚠️ Muammo", "Muammo"),
    "info": ("ℹ️ Savol", "Savol"),
}

INSTANT_TYPES = frozenset({"call_staff", "check_client"})


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🙋 Iltimos, xizmat ko'rsating", callback_data="req:call_staff")
    kb.button(text="👀 Ombordagi mijozga qarang", callback_data="req:check_client")
    kb.button(text="📦 Tovar / mahsulot buyurtma", callback_data="req:product_order")
    kb.button(text="📋 Mahsulot olib keling", callback_data="req:bring_product")
    kb.button(text="⭐ VIP / Shoshilinch", callback_data="req:vip")
    kb.button(text="⚠️ Muammo / shikoyat", callback_data="req:complaint")
    kb.button(text="ℹ️ Savol / ma'lumot", callback_data="req:info")
    kb.button(text="📋 Mening arizalarim", callback_data="my_orders")
    kb.adjust(1)
    return kb.as_markup()


def back_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Asosiy menyu", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def confirm_instant(request_type: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha, yuborish", callback_data=f"send:{request_type}")
    kb.button(text="◀️ Bekor", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def group_actions(order_id: int, order: dict, viewer_id: int | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    status = order["status"]
    assignee_id = order.get("assigned_to_id")

    if status == "yangi":
        kb.button(text="👷 Men xizmat ko'rsataman", callback_data=f"act:{order_id}:band")
        kb.button(text="❌ Rad etish", callback_data=f"act:{order_id}:rad")
    elif status == "jarayonda":
        if viewer_id is None or viewer_id == assignee_id:
            kb.button(text="✔️ Xizmat tugadi", callback_data=f"act:{order_id}:tugadi")
        else:
            kb.button(
                text=f"🔒 {order.get('assigned_to', 'Xodim')} xizmatda",
                callback_data="noop",
            )
    else:
        label = STATUSES.get(status, status)
        if status == "bajarildi":
            label = f"✔️ {format_duration(order)}"
        kb.button(text=label, callback_data="noop")
    kb.adjust(1)
    return kb.as_markup()


def report_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Bugungi hisobot", callback_data="report:today")
    kb.button(text="👷 Xodimlar bo'yicha", callback_data="report:staff")
    kb.button(text="📈 Umumiy holat", callback_data="report:all")
    kb.adjust(1)
    return kb.as_markup()
