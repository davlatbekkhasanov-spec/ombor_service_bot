import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from config import is_admin, settings
from keyboards import (
    INSTANT_TYPES,
    REQUEST_TYPES,
    back_menu,
    confirm_instant,
    group_actions,
    main_menu,
    report_menu,
)
from storage import (
    create_order,
    get_order,
    init_db,
    recent_orders,
    set_group_message,
    stats_all_status,
    stats_today,
    update_status,
    user_orders,
)
from ui import (
    instant_confirm_text,
    instant_order_text,
    notify_user_status,
    order_card,
    prompt_for_type,
    report_all_card,
    report_today_card,
    user_orders_card,
    welcome_card,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

cfg = settings()
BOT_TOKEN = cfg["bot_token"]
GROUP_ID = cfg["group_id"]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class OrderForm(StatesGroup):
    waiting_text = State()


def _is_group_chat(chat_id: int) -> bool:
    return GROUP_ID is not None and chat_id == GROUP_ID


async def _notify_group(order_id: int) -> Message | None:
    order = get_order(order_id)
    if not order or not GROUP_ID:
        return None
    try:
        msg = await bot.send_message(
            GROUP_ID,
            order_card(order, for_group=True),
            parse_mode="HTML",
            reply_markup=group_actions(order_id, order["status"]),
        )
        set_group_message(order_id, msg.message_id)
        log.info("Guruhga #%s yuborildi", order_id)
        return msg
    except Exception:
        log.exception("Guruhga yuborish xato #%s", order_id)
        return None


async def _create_order_for_user(
    *,
    user_id: int,
    username: str | None,
    full_name: str | None,
    request_type: str,
    text: str,
) -> tuple[int, bool]:
    kind_label, prefix = REQUEST_TYPES[request_type]
    body = text if text.startswith(prefix) else f"{prefix}:\n{text}"
    order_id = create_order(
        user_id=user_id,
        username=username,
        full_name=full_name,
        request_type=request_type,
        kind_label=kind_label,
        text=body,
    )
    sent = await _notify_group(order_id) is not None
    return order_id, sent


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(welcome_card(), parse_mode="HTML", reply_markup=main_menu())


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=main_menu())


@dp.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_menu())


@dp.message(Command("id"))
async def cmd_id(message: Message):
    await message.answer(
        f"Chat ID: <code>{message.chat.id}</code>\n"
        f"Turi: {message.chat.type}",
        parse_mode="HTML",
    )


@dp.message(Command("stat", "hisobot", "report"))
async def cmd_report(message: Message):
    if message.chat.type == ChatType.PRIVATE and not is_admin(message.from_user.id):
        await message.answer("Hisobot faqat guruhda yoki admin uchun.")
        return
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if not _is_group_chat(message.chat.id):
            return
    await message.answer(report_today_card(stats_today()), parse_mode="HTML", reply_markup=report_menu())


@dp.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("Asosiy menyu:", reply_markup=main_menu())
    await call.answer()


@dp.callback_query(F.data == "my_orders")
async def cb_my_orders(call: CallbackQuery):
    rows = user_orders(call.from_user.id)
    await call.message.answer(
        user_orders_card(rows),
        parse_mode="HTML",
        reply_markup=back_menu(),
    )
    await call.answer()


@dp.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()


@dp.callback_query(F.data.startswith("req:"))
async def cb_request_type(call: CallbackQuery, state: FSMContext):
    request_type = call.data.split(":", 1)[1]
    if request_type not in REQUEST_TYPES:
        await call.answer("Noto'g'ri tanlov", show_alert=True)
        return
    if request_type in INSTANT_TYPES:
        await call.message.answer(
            instant_confirm_text(request_type),
            parse_mode="HTML",
            reply_markup=confirm_instant(request_type),
        )
    else:
        await state.set_state(OrderForm.waiting_text)
        await state.update_data(request_type=request_type)
        await call.message.answer(
            prompt_for_type(request_type),
            parse_mode="HTML",
            reply_markup=back_menu(),
        )
    await call.answer()


@dp.callback_query(F.data.startswith("send:"))
async def cb_send_instant(call: CallbackQuery, state: FSMContext):
    await state.clear()
    request_type = call.data.split(":", 1)[1]
    if request_type not in INSTANT_TYPES:
        await call.answer("Xato", show_alert=True)
        return
    text = instant_order_text(request_type)
    order_id, sent = await _create_order_for_user(
        user_id=call.from_user.id,
        username=call.from_user.username,
        full_name=call.from_user.full_name,
        request_type=request_type,
        text=text,
    )
    extra = ""
    if not sent:
        extra = "\n\n⚠️ Guruhga xabar ketmadi — GROUP_ID ni tekshiring."
    await call.message.answer(
        f"✅ Ariza yuborildi!\nRaqam: <b>#{order_id}</b>{extra}\n\n"
        "Guruh javobini kuting — holat o'zgarganda xabar olasiz.",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )
    await call.answer("Yuborildi!")


@dp.message(StateFilter(OrderForm.waiting_text), F.chat.type == ChatType.PRIVATE, F.text)
async def save_text_order(message: Message, state: FSMContext):
    data = await state.get_data()
    request_type = data.get("request_type", "product_order")
    if request_type not in REQUEST_TYPES:
        request_type = "product_order"
    order_id, sent = await _create_order_for_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        request_type=request_type,
        text=message.text.strip(),
    )
    await state.clear()
    extra = ""
    if not sent:
        extra = "\n\n⚠️ Guruhga xabar ketmadi — GROUP_ID ni tekshiring."
    await message.answer(
        f"✅ Ariza qabul qilindi!\nRaqam: <b>#{order_id}</b>{extra}\n\n"
        "Ombor guruhi tez orada ko'radi va qabul qiladi.",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


@dp.callback_query(F.data.startswith("act:"))
async def cb_group_action(call: CallbackQuery):
    if call.message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await call.answer("Faqat guruhda", show_alert=True)
        return
    if not _is_group_chat(call.message.chat.id):
        await call.answer("Bu guruh emas", show_alert=True)
        return

    parts = call.data.split(":")
    if len(parts) != 3:
        await call.answer("Xato", show_alert=True)
        return
    order_id = int(parts[1])
    new_status = parts[2]

    order = get_order(order_id)
    if not order:
        await call.answer("Ariza topilmadi", show_alert=True)
        return

    if order["status"] in ("bajarildi", "rad") and new_status != order["status"]:
        await call.answer("Bu ariza allaqachon yopilgan", show_alert=True)
        return

    actor = call.from_user.full_name or call.from_user.username or "Xodim"
    updated = update_status(
        order_id,
        new_status,
        actor_name=actor,
        actor_id=call.from_user.id,
    )
    if not updated:
        await call.answer("Xato", show_alert=True)
        return

    try:
        await call.message.edit_text(
            order_card(updated, for_group=True),
            parse_mode="HTML",
            reply_markup=group_actions(order_id, new_status),
        )
    except Exception:
        log.exception("Guruh xabarini yangilash xato")

    try:
        await bot.send_message(
            updated["user_id"],
            notify_user_status(updated),
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
    except Exception:
        log.warning("Foydalanuvchiga xabar ketmadi user=%s", updated["user_id"])

    labels = {
        "qabul": "Qabul qilindi",
        "jarayonda": "Jarayonda",
        "bajarildi": "Bajarildi",
        "rad": "Rad etildi",
    }
    await call.answer(labels.get(new_status, "Yangilandi"))


@dp.callback_query(F.data.startswith("report:"))
async def cb_report(call: CallbackQuery):
    if call.message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if not _is_group_chat(call.message.chat.id):
            await call.answer("Ruxsat yo'q", show_alert=True)
            return
    elif not is_admin(call.from_user.id):
        await call.answer("Admin uchun", show_alert=True)
        return

    kind = call.data.split(":", 1)[1]
    if kind == "today":
        text = report_today_card(stats_today())
    else:
        text = report_all_card(stats_all_status(), recent_orders(10))
    await call.message.answer(text, parse_mode="HTML", reply_markup=report_menu())
    await call.answer()


@dp.message(Command("orders"))
async def cmd_orders(message: Message):
    if not is_admin(message.from_user.id):
        return
    rows = recent_orders(12)
    if not rows:
        await message.answer("Arizalar yo'q.")
        return
    from ui import status_label
    from html import escape

    lines = ["📋 <b>Oxirgi arizalar</b>\n"]
    for r in rows:
        lines.append(
            f"#{r['id']} {status_label(r['status'])}\n"
            f"{escape(r['full_name'] or '—')} · {escape(r['kind_label'])}\n"
            f"{escape(r['text'][:100])}\n"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


async def main():
    init_db()
    if GROUP_ID is None:
        log.warning("GROUP_ID sozlanmagan")
    else:
        log.info("Guruh: %s", GROUP_ID)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
