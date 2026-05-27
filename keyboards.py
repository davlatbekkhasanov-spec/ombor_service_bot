"""Tugmalar."""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from storage import STATUSES

# request_type -> (label, prefix for text)
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


def group_actions(order_id: int, status: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if status == "yangi":
        kb.button(text="✅ Qabul qilish", callback_data=f"act:{order_id}:qabul")
        kb.button(text="❌ Rad etish", callback_data=f"act:{order_id}:rad")
    elif status == "qabul":
        kb.button(text="🔄 Jarayonda", callback_data=f"act:{order_id}:jarayonda")
        kb.button(text="✔️ Bajarildi", callback_data=f"act:{order_id}:bajarildi")
        kb.button(text="❌ Rad etish", callback_data=f"act:{order_id}:rad")
    elif status == "jarayonda":
        kb.button(text="✔️ Bajarildi", callback_data=f"act:{order_id}:bajarildi")
        kb.button(text="❌ Rad etish", callback_data=f"act:{order_id}:rad")
    else:
        kb.button(text=f"Holat: {STATUSES.get(status, status)}", callback_data="noop")
    kb.adjust(2)
    return kb.as_markup()


def report_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Bugungi hisobot", callback_data="report:today")
    kb.button(text="📈 Umumiy holat", callback_data="report:all")
    kb.adjust(1)
    return kb.as_markup()
