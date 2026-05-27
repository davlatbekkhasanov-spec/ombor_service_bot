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
from live_ticker import LiveTicker
from keyboards import (
    INSTANT_TYPES,
    REQUEST_TYPES,
    back_menu,
    group_actions,
    main_menu,
    report_menu,
)
from storage import (
    assign_to_staff,
    complete_order,
    create_order,
    get_order,
    init_db,
    join_staff,
    recent_orders,
    reject_order,
    set_group_message,
    stats_all_status,
    stats_today,
)
from ui import (
    customer_done,
    customer_rejected,
    customer_sent,
    instant_order_text,
    order_card,
    format_duration,
    prompt_for_type,
    report_all_card,
    report_staff_card,
    report_today_card,
    service_done_group_card,
    welcome_card,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

cfg = settings()
BOT_TOKEN = cfg["bot_token"]
GROUP_ID = cfg["group_id"]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
_ticker: LiveTicker | None = None


class OrderForm(StatesGroup):
    waiting_text = State()


def _is_group_chat(chat_id: int) -> bool:
    return GROUP_ID is not None and chat_id == GROUP_ID


def _staff_name(user) -> str:
    return user.full_name or user.username or f"Xodim {user.id}"


async def _refresh_group_message(order: dict, viewer_id: int | None = None) -> None:
    msg_id = order.get("group_message_id")
    if not msg_id or not GROUP_ID:
        return
    try:
        await bot.edit_message_text(
            order_card(order, for_group=True, live=True),
            chat_id=GROUP_ID,
            message_id=msg_id,
            parse_mode="HTML",
            reply_markup=group_actions(order["id"], order, viewer_id),
        )
    except Exception:
        log.exception("Guruh xabarini yangilash xato #%s", order["id"])


async def _notify_group(order_id: int) -> Message | None:
    order = get_order(order_id)
    if not order or not GROUP_ID:
        return None
    try:
        msg = await bot.send_message(
            GROUP_ID,
            order_card(order, for_group=True, live=True),
            parse_mode="HTML",
            reply_markup=group_actions(order_id, order),
        )
        set_group_message(order_id, msg.message_id)
        log.info("Guruhga #%s yuborildi", order_id)
        if _ticker:
            await _ticker.tick_once()
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
        text = instant_order_text(request_type)
        order_id, sent = await _create_order_for_user(
            user_id=call.from_user.id,
            username=call.from_user.username,
            full_name=call.from_user.full_name,
            request_type=request_type,
            text=text,
        )
        extra = "\n⚠️ Guruhga xabar ketmadi." if not sent else ""
        await call.message.answer(
            customer_sent(order_id) + extra,
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
        await call.answer("Yuborildi!")
    else:
        await state.set_state(OrderForm.waiting_text)
        await state.update_data(request_type=request_type)
        await call.message.answer(
            prompt_for_type(request_type),
            parse_mode="HTML",
            reply_markup=back_menu(),
        )
        await call.answer()


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
        extra = "\n⚠️ Guruhga xabar ketmadi."
    await message.answer(
        customer_sent(order_id) + extra,
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
    action = parts[2]
    staff_id = call.from_user.id
    staff_name = _staff_name(call.from_user)

    if action == "band":
        updated, err = assign_to_staff(order_id, staff_id, staff_name)
        if err:
            await call.answer(err, show_alert=True)
            return
        await _refresh_group_message(updated, staff_id)
        await call.answer(f"#{order_id} band qilindi")

    elif action == "qoshil":
        updated, err = join_staff(order_id, staff_id, staff_name)
        if err:
            await call.answer(err, show_alert=True)
            return
        await _refresh_group_message(updated, staff_id)
        await call.answer(f"#{order_id} jamoaga qo'shildingiz")

    elif action == "tugadi":
        updated, err = complete_order(order_id, staff_id)
        if err:
            await call.answer(err, show_alert=True)
            return
        await _refresh_group_message(updated, staff_id)
        try:
            await bot.send_message(
                GROUP_ID,
                service_done_group_card(updated),
                parse_mode="HTML",
            )
        except Exception:
            pass
        try:
            await bot.send_message(
                updated["user_id"],
                customer_done(updated),
                parse_mode="HTML",
                reply_markup=main_menu(),
            )
        except Exception:
            log.warning("Mijozga tugatish xabari ketmadi")
        await call.answer(f"Tugadi! {format_duration(updated)}")

    elif action == "rad":
        order = get_order(order_id)
        if order and order["status"] != "yangi":
            await call.answer("Faqat yangi arizani rad etish mumkin", show_alert=True)
            return
        updated = reject_order(order_id)
        if not updated:
            await call.answer("Rad etib bo'lmadi", show_alert=True)
            return
        await _refresh_group_message(updated, staff_id)
        try:
            await bot.send_message(
                updated["user_id"],
                customer_rejected(order_id),
                parse_mode="HTML",
                reply_markup=main_menu(),
            )
        except Exception:
            pass
        await call.answer("Rad etildi")
    else:
        await call.answer("Noma'lum amal", show_alert=True)


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
    stats = stats_today()
    if kind == "today":
        text = report_today_card(stats)
    elif kind == "staff":
        text = report_staff_card(stats)
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
    from html import escape

    from ui import status_label

    lines = ["📋 <b>Oxirgi arizalar</b>\n"]
    for r in rows:
        staff = f" · {escape(r.get('staff_names') or r.get('assigned_to') or '')}" if (
            r.get("staff_names") or r.get("assigned_to")
        ) else ""
        dur = f" · {format_duration(r)}" if (
            r.get("service_seconds") is not None or r.get("service_minutes") is not None
        ) else ""
        lines.append(
            f"#{r['id']} {status_label(r['status'])}{staff}{dur}\n"
            f"{escape(r['full_name'] or '—')} · {escape(r['kind_label'])}\n"
            f"{escape(r['text'][:100])}\n"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


async def main():
    global _ticker
    init_db()
    if GROUP_ID is None:
        log.warning("GROUP_ID sozlanmagan")
    else:
        log.info("Guruh: %s", GROUP_ID)
        _ticker = LiveTicker(bot, GROUP_ID)
        _ticker.start()
    await dp.start_polling(bot)
    if _ticker:
        _ticker.stop()


if __name__ == "__main__":
    asyncio.run(main())
