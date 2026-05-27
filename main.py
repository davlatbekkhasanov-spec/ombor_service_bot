import asyncio
import logging
import os
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")


def _parse_group_id() -> int | None:
    raw = (os.getenv("GROUP_ID") or "").strip().strip('"').strip("'")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        log.error("GROUP_ID noto'g'ri: %r", raw)
        return None


GROUP_ID = _parse_group_id()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

DB_NAME = "orders.db"

ORDER_KINDS = {
    "new_order": ("📦 Заявка", "Заявка"),
    "service": ("👷 Хизмат", "Хизмат"),
    "vip": ("⭐ VIP", "VIP"),
}


class OrderForm(StatesGroup):
    waiting_text = State()


def db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            full_name TEXT,
            text TEXT,
            status TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    return conn


def menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Заявка бериш", callback_data="new_order")
    kb.button(text="👷 Ходим билан хизмат", callback_data="service")
    kb.button(text="⭐ VIP / Срочно", callback_data="vip")
    kb.button(text="📋 Статус", callback_data="status")
    kb.adjust(1)
    return kb.as_markup()


def _order_prompt(kind_key: str) -> str:
    if kind_key == "new_order":
        return (
            "📦 Заявка учун товарларни ёзинг.\n\n"
            "Масалан:\n"
            "1. Cola 1L — 12 dona\n"
            "2. Pechenye — 4 quti\n\n"
            "Faqat matn yuboring — «Заявка:» yozish shart emas."
        )
    if kind_key == "service":
        return (
            "👷 Ходим билан хизмат.\n\n"
            "Нима кераклигини қисқача ёзинг.\n"
            "Faqat matn yuboring — «Хизмат:» yozish shart emas."
        )
    return (
        "⭐ VIP / Срочно.\n\n"
        "Мижоз / бўлим / товарларни ёзинг.\n"
        "Faqat matn yuboring — «VIP:» yozish shart emas."
    )


async def _save_and_notify(message: Message, order_text: str, kind_label: str) -> int:
    conn = db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO orders (user_id, username, full_name, text, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            message.from_user.id,
            message.from_user.username,
            message.from_user.full_name,
            order_text,
            "Янги",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ),
    )
    order_id = cur.lastrowid
    conn.commit()
    conn.close()

    if not GROUP_ID:
        log.warning("GROUP_ID yo'q — #%s guruhga yuborilmadi", order_id)
        return order_id

    username = message.from_user.username
    user_line = f"@{username}" if username else "—"
    group_text = (
        f"🆕 {kind_label} #{order_id}\n\n"
        f"Кимдан: {message.from_user.full_name}\n"
        f"Username: {user_line}\n"
        f"User ID: <code>{message.from_user.id}</code>\n\n"
        f"{order_text}"
    )
    try:
        await bot.send_message(GROUP_ID, group_text, parse_mode="HTML")
        log.info("Guruhga yuborildi: #%s -> %s", order_id, GROUP_ID)
    except Exception:
        log.exception("Guruhga yuborish xato #%s, GROUP_ID=%s", order_id, GROUP_ID)
        await message.answer(
            "⚠️ Заявка saqlandi, lekin guruhga xabar ketmadi.\n"
            "Bot guruhda admin ekanini va GROUP_ID to'g'riligini tekshiring."
        )

    return order_id


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Ассалому алайкум!\n\n"
        "Омбор хизмати боти.\n"
        "Керакли режимни танланг:",
        reply_markup=menu(),
    )


@dp.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=menu())


@dp.callback_query(F.data.in_(ORDER_KINDS.keys()))
async def pick_order_kind(call: CallbackQuery, state: FSMContext):
    await state.set_state(OrderForm.waiting_text)
    await state.update_data(kind=call.data)
    await call.message.answer(_order_prompt(call.data))
    await call.answer()


@dp.callback_query(F.data == "status")
async def status(call: CallbackQuery):
    conn = db()
    rows = conn.execute(
        "SELECT id, status, created_at FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 5",
        (call.from_user.id,),
    ).fetchall()
    conn.close()

    if not rows:
        await call.message.answer("Ҳали заявка йўқ.")
    else:
        text = "Охирги заявкалар:\n\n"
        for r in rows:
            text += f"#{r[0]} — {r[1]} — {r[2]}\n"
        await call.message.answer(text)

    await call.answer()


@dp.message(Command("id"))
async def chat_id(message: Message):
    await message.answer(
        f"Chat ID: <code>{message.chat.id}</code>\n"
        f"Turi: {message.chat.type}",
        parse_mode="HTML",
    )


@dp.message(StateFilter(OrderForm.waiting_text), F.chat.type == ChatType.PRIVATE, F.text)
async def save_from_state(message: Message, state: FSMContext):
    data = await state.get_data()
    kind_key = data.get("kind", "new_order")
    _, prefix = ORDER_KINDS.get(kind_key, ORDER_KINDS["new_order"])
    kind_label, _ = ORDER_KINDS.get(kind_key, ORDER_KINDS["new_order"])
    order_text = f"{prefix}:\n{message.text.strip()}"
    order_id = await _save_and_notify(message, order_text, kind_label)
    await state.clear()
    await message.answer(
        f"✅ Заявка қабул қилинди. Рақам: #{order_id}",
        reply_markup=menu(),
    )


@dp.message(F.text.startswith(("Заявка:", "Хизмат:", "VIP:")), F.chat.type == ChatType.PRIVATE)
async def save_order_with_prefix(message: Message, state: FSMContext):
    await state.clear()
    text = message.text.strip()
    if text.startswith("VIP:"):
        kind_label = "⭐ VIP"
    elif text.startswith("Хизмат:"):
        kind_label = "👷 Хизмат"
    else:
        kind_label = "📦 Заявка"
    order_id = await _save_and_notify(message, text, kind_label)
    await message.answer(
        f"✅ Заявка қабул қилинди. Рақам: #{order_id}",
        reply_markup=menu(),
    )


@dp.message(Command("orders"))
async def orders(message: Message):
    conn = db()
    rows = conn.execute(
        "SELECT id, full_name, text, status, created_at FROM orders ORDER BY id DESC LIMIT 10"
    ).fetchall()
    conn.close()

    if not rows:
        await message.answer("Заявкalar yo'q.")
        return

    text = "📋 Oxirgi заявkalar:\n\n"
    for r in rows:
        text += f"#{r[0]} | {r[3]} | {r[4]}\n{r[1]}: {r[2][:80]}\n\n"

    await message.answer(text)


async def main():
    db()
    if GROUP_ID is None:
        log.warning("GROUP_ID sozlanmagan — guruhga xabar yuborilmaydi")
    else:
        log.info("Guruhga xabarlar: %s", GROUP_ID)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
