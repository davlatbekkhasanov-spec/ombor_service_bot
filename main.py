import os
import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")


def _parse_group_id() -> int | None:
    raw = (os.getenv("GROUP_ID") or "").strip().strip('"').strip("'")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


GROUP_ID = _parse_group_id()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DB_NAME = "orders.db"


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


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Ассалому алайкум!\n\n"
        "Омбор хизмати боти.\n"
        "Керакли режимни танланг:",
        reply_markup=menu()
    )


@dp.callback_query(F.data == "new_order")
async def new_order(call: CallbackQuery):
    await call.message.answer(
        "📦 Заявкани шу форматда юборинг:\n\n"
        "Заявка:\n"
        "1. Cola 1L - 12 dona\n"
        "2. Pechenye - 4 quti\n"
        "3. Shampun - 2 dona"
    )
    await call.answer()


@dp.callback_query(F.data == "service")
async def service(call: CallbackQuery):
    await call.message.answer(
        "👷 Ходим билан хизмат учун ёзинг:\n\n"
        "Хизмат:\n"
        "Нима кераклигини қисқача ёзинг."
    )
    await call.answer()


@dp.callback_query(F.data == "vip")
async def vip(call: CallbackQuery):
    await call.message.answer(
        "⭐ VIP / Срочно заявка учун ёзинг:\n\n"
        "VIP:\n"
        "Мижоз / бўлим / товарлар."
    )
    await call.answer()


@dp.callback_query(F.data == "status")
async def status(call: CallbackQuery):
    conn = db()
    rows = conn.execute(
        "SELECT id, status, created_at FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 5",
        (call.from_user.id,)
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


@dp.message(F.text.startswith(("Заявка:", "Хизмат:", "VIP:")), F.chat.type == ChatType.PRIVATE)
async def save_order(message: Message):
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
            message.text,
            "Янги",
            datetime.now().strftime("%Y-%m-%d %H:%M")
        )
    )
    order_id = cur.lastrowid
    conn.commit()
    conn.close()

    await message.answer(f"✅ Заявка қабул қилинди. Рақам: #{order_id}")

    if GROUP_ID:
        username = message.from_user.username
        user_line = f"@{username}" if username else "—"
        await bot.send_message(
            GROUP_ID,
            f"🆕 Янги заявка #{order_id}\n\n"
            f"Кимдан: {message.from_user.full_name}\n"
            f"Username: {user_line}\n"
            f"User ID: <code>{message.from_user.id}</code>\n\n"
            f"{message.text}",
            parse_mode="HTML",
        )


@dp.message(Command("orders"))
async def orders(message: Message):
    conn = db()
    rows = conn.execute(
        "SELECT id, full_name, text, status, created_at FROM orders ORDER BY id DESC LIMIT 10"
    ).fetchall()
    conn.close()

    if not rows:
        await message.answer("Заявкалар йўқ.")
        return

    text = "📋 Охирги заявкалар:\n\n"
    for r in rows:
        text += f"#{r[0]} | {r[3]} | {r[4]}\n{r[1]}: {r[2][:80]}\n\n"

    await message.answer(text)


async def main():
    db()
    if GROUP_ID is None:
        print("⚠️  GROUP_ID sozlanmagan — guruhga xabar yuborilmaydi. /id bilan ID oling.")
    else:
        print(f"✅ Guruhga xabarlar: {GROUP_ID}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
