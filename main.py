import asyncio
import html
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from config import admin_notify_id, is_admin, settings
from live_ticker import LiveTicker, refresh_order_message
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
    attach_staff,
    cancel_service_order,
    complete_order,
    create_order,
    get_order,
    init_db,
    join_staff,
    list_active_service_staff,
    recent_orders,
    reject_order,
    set_group_message,
    staff_ids_on_order,
    staff_today_hub_summary,
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
from backup_scheduler import run_daily_backup
from baseline_restore import ensure_baseline_restored
from db_backup import (
    export_payload,
    payload_to_json_bytes,
    payload_to_orders_csv,
    restore_all_from_json,
    write_backup_files,
)
from persist_data import persistence_status_line
from startup_health import collect_db_stats, format_startup_admin_message
from storage import DB_NAME

TZ = ZoneInfo(os.getenv("TZ", "Asia/Tashkent"))
from yordamchi_push import (
    push_session_end_background,
    push_session_start_background,
    push_to_yordamchi_hub,
    push_to_yordamchi_hub_background,
    today_iso,
)
from telegram_safe import run_telegram

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


def _live_service_start(*, staff_id: int, staff_name: str, order: dict) -> None:
    push_session_start_background(
        tg_id=staff_id,
        bot_key="ombor",
        user_name=staff_name,
        activity_type="ombor",
        metadata={"order_id": int(order.get("id") or 0), "kind": order.get("kind_label") or ""},
    )


def _live_service_end(staff_id: int) -> None:
    if staff_id:
        push_session_end_background(tg_id=staff_id, bot_key="ombor", activity_type="ombor")


def _live_service_end_for_order(order: dict) -> None:
    seen: set[int] = set()
    for sid in staff_ids_on_order(int(order.get("id") or 0)):
        if sid not in seen:
            _live_service_end(sid)
            seen.add(sid)
    lead = int(order.get("assigned_to_id") or 0)
    if lead and lead not in seen:
        _live_service_end(lead)


def _reconcile_hub_live_sessions() -> None:
    from hub_live_sync import reconcile_hub_live_sessions

    reconcile_hub_live_sessions()


async def _answer_stale_order(call: CallbackQuery, order: dict, err: str) -> None:
    await _refresh_group_message(order, call.from_user.id, force=True)
    await call.answer(f"{err}\n(Xabar yangilandi)", show_alert=True)


async def _refresh_group_message(order: dict, viewer_id: int | None = None) -> None:
    if not GROUP_ID:
        return
    await refresh_order_message(
        bot,
        GROUP_ID,
        order,
        viewer_id=viewer_id,
        force=True,
    )


async def _sync_group_order(order_id: int, viewer_id: int | None = None) -> None:
    order = get_order(order_id)
    if order:
        await _refresh_group_message(order, viewer_id)


async def _notify_group(order_id: int) -> Message | None:
    order = get_order(order_id)
    if not order or not GROUP_ID:
        return None

    async def _send() -> Message:
        return await bot.send_message(
            GROUP_ID,
            order_card(order, for_group=True, live=True),
            parse_mode="HTML",
            reply_markup=group_actions(order_id, order),
        )

    try:
        msg = await run_telegram(_send, label=f"send #{order_id}", force=True)
        if not msg:
            log.warning("Guruhga #%s yuborilmadi (flood yoki xato)", order_id)
            return None
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


async def _clear_stale_group_order(call: CallbackQuery, order_id: int) -> None:
    """Bazada yo'q eski guruh xabarini tugmasiz qilish."""
    if not call.message or not GROUP_ID:
        return
    try:
        await bot.edit_message_text(
            f"⚠️ <b>Ariza #{order_id}</b> bazada topilmadi.\n"
            "Eski xabar — yangi so'rov yuboring.",
            chat_id=GROUP_ID,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=None,
        )
    except Exception:
        pass


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

    order = get_order(order_id)
    if not order:
        await _clear_stale_group_order(call, order_id)
        await call.answer(
            f"Ariza #{order_id} bazada yo'q (eski xabar yangilandi)",
            show_alert=True,
        )
        return
    order = attach_staff(order)

    if action == "band":
        updated, err = assign_to_staff(order_id, staff_id, staff_name)
        if err:
            await _sync_group_order(order_id, staff_id)
            await call.answer(err, show_alert=True)
            return
        await _refresh_group_message(updated, staff_id)
        _live_service_start(staff_id=staff_id, staff_name=staff_name, order=updated)
        await call.answer(f"#{order_id} band qilindi")

    elif action == "qoshil":
        updated, err = join_staff(order_id, staff_id, staff_name)
        if err:
            fresh = attach_staff(get_order(order_id) or order)
            await _answer_stale_order(call, fresh, err)
            return
        await _refresh_group_message(updated, staff_id)
        _live_service_start(staff_id=staff_id, staff_name=staff_name, order=updated)
        await call.answer(f"#{order_id} jamoaga qo'shildingiz")

    elif action == "tugadi":
        if order["status"] == "bajarildi":
            _live_service_end_for_order(order)
            await _refresh_group_message(order, staff_id, force=True)
            await call.answer("Bu ariza allaqachon tugagan", show_alert=True)
            return
        if order["status"] == "yangi":
            await call.answer(
                "Avval «Men xizmat ko'rsataman» bosing",
                show_alert=True,
            )
            return
        if order["status"] != "jarayonda":
            _live_service_end_for_order(order)
            await _answer_stale_order(call, order, "Bu ariza yopilgan")
            return
        updated, err = complete_order(order_id, staff_id)
        if err:
            fresh = attach_staff(get_order(order_id) or order)
            if fresh.get("status") in ("bajarildi", "rad"):
                _live_service_end_for_order(fresh)
            await _answer_stale_order(call, fresh, err)
            return
        await _refresh_group_message(updated, staff_id, force=True)
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
        push_to_yordamchi_hub_background(
            tg_id=staff_id,
            bot_key="ombor",
            summary=staff_today_hub_summary(staff_id, today_iso()),
        )
        _live_service_end_for_order(updated)
        await call.answer(f"Tugadi! {format_duration(updated)}")

    elif action == "rad":
        if order["status"] == "bajarildi":
            _live_service_end_for_order(order)
            await _refresh_group_message(order, staff_id, force=True)
            await call.answer("Bu ariza allaqachon tugagan", show_alert=True)
            return
        if order["status"] == "jarayonda":
            updated, err = cancel_service_order(
                order_id,
                staff_id,
                admin=is_admin(staff_id),
            )
            if not updated:
                fresh = attach_staff(get_order(order_id) or order)
                await _answer_stale_order(call, fresh, err or "Rad etib bo'lmadi")
                return
            await _refresh_group_message(updated, staff_id, force=True)
            try:
                await bot.send_message(
                    updated["user_id"],
                    customer_rejected(order_id),
                    parse_mode="HTML",
                    reply_markup=main_menu(),
                )
            except Exception:
                pass
            _live_service_end_for_order(updated)
            await call.answer("Xizmat bekor qilindi")
            return
        if order["status"] == "rad":
            _live_service_end_for_order(order)
            await _refresh_group_message(order, staff_id, force=True)
            await call.answer("Allaqachon rad etilgan", show_alert=True)
            return
        updated = reject_order(order_id)
        if not updated:
            fresh = attach_staff(get_order(order_id) or order)
            await _answer_stale_order(call, fresh, "Rad etib bo'lmadi")
            return
        await _refresh_group_message(updated, staff_id, force=True)
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


@dp.message(Command("seedstatus"))
async def cmd_seedstatus(message: Message):
    if not is_admin(message.from_user.id):
        return
    from orders_seed import ORDERS_SEED_NOTE, ORDERS_SEED_ROWS, ORDERS_SEED_VERSION
    from storage import _conn

    conn = _conn()
    meta = conn.execute(
        "SELECT version, applied_at, note FROM orders_seed_meta WHERE id = 1"
    ).fetchone()
    total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    done = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE status='bajarildi'"
    ).fetchone()[0]
    conn.close()
    st = stats_all_status()
    today = stats_today()
    lines = [
        "📦 <b>Seed holati</b>",
        f"Kod: v{ORDERS_SEED_VERSION} · {len(ORDERS_SEED_ROWS)} ta qator",
        f"Matn: {ORDERS_SEED_NOTE}",
    ]
    if meta:
        lines.append(f"DB meta: v{meta[0]} · {meta[1]}")
        if meta[2]:
            lines.append(f"DB izoh: {meta[2]}")
    lines.append(f"SQLite: jami <b>{total}</b> · bajarildi <b>{done}</b>")
    lines.append(f"Bugun: <b>{today['total_today']}</b> ta · {today['date']}")
    if st:
        parts = ", ".join(f"{k}={v}" for k, v in sorted(st.items()))
        lines.append(f"Holatlar: {parts}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("backup"))
async def cmd_backup(message: Message):
    if message.chat.type != ChatType.PRIVATE or not is_admin(message.from_user.id):
        return
    await message.answer("⏳ Zaxira tayyorlanmoqda…")
    try:
        payload = export_payload(DB_NAME)
        counts = payload.get("counts", {})
        stamp = datetime.now(TZ).strftime("%Y%m%d_%H%M%S")
        for name, data in (
            (f"backup_{stamp}.json", payload_to_json_bytes(payload)),
            (f"orders_{stamp}.csv", payload_to_orders_csv(payload)),
        ):
            await message.answer_document(
                BufferedInputFile(data, filename=name),
                caption=name,
            )
        lines = [
            "✅ Zaxira tayyor",
            f"DB: <code>{html.escape(DB_NAME)}</code>",
            "",
            "Jadval yozuvlari:",
        ]
        for t, c in counts.items():
            lines.append(f"  • {t}: {c}")
        lines.append("")
        lines.append("Deploydan oldin shu fayllarni saqlang.")
        lines.append("Tiklash: backup JSON faylini shu chatga yuboring.")
        await message.answer("\n".join(lines), parse_mode="HTML")
    except Exception as exc:
        log.exception("backup")
        await message.answer(f"❌ Zaxira xato: {html.escape(str(exc))}", parse_mode="HTML")


@dp.message(
    F.document,
    F.chat.type == ChatType.PRIVATE,
)
async def restore_backup_document(message: Message):
    if not is_admin(message.from_user.id):
        return
    doc = message.document
    if not doc or not (doc.file_name or "").lower().endswith(".json"):
        return
    tmp = os.path.join(os.path.dirname(DB_NAME) or ".", "_restore_upload.json")
    try:
        f = await bot.get_file(doc.file_id)
        await bot.download_file(f.file_path, tmp)
        res = await asyncio.to_thread(
            restore_all_from_json, DB_NAME, tmp, True
        )
        if res.get("ok"):
            await message.answer(
                "✅ Tiklandi\n"
                f"Arizalar: {res.get('orders', 0)}\n"
                f"Xodimlar: {res.get('staff', 0)}",
                parse_mode="HTML",
            )
        else:
            await message.answer(f"❌ {html.escape(res.get('message', 'xato'))}", parse_mode="HTML")
    except Exception as exc:
        log.exception("restore backup")
        await message.answer(f"❌ Tiklash xato: {html.escape(str(exc))}", parse_mode="HTML")
    finally:
        try:
            if os.path.isfile(tmp):
                os.remove(tmp)
        except OSError:
            pass


async def main():
    global _ticker
    log.info(persistence_status_line(DB_NAME))
    try:
        if os.path.isfile(DB_NAME):
            write_backup_files(DB_NAME, os.path.join(os.path.dirname(DB_NAME) or ".", "backups"))
    except Exception:
        log.exception("Startup JSON zaxira xato")
    init_db()
    try:
        br = ensure_baseline_restored(DB_NAME)
        if br.get("restored"):
            log.warning(
                "DB tiklandi (%s): %s -> %s ariza",
                br.get("source"),
                br.get("before"),
                br.get("after"),
            )
    except Exception:
        log.exception("Baseline tiklash xato")
    asyncio.create_task(run_daily_backup(DB_NAME))
    try:
        from orders_seed import ORDERS_SEED_ROWS, ORDERS_SEED_VERSION

        all_s = stats_all_status()
        log.info(
            "DB tayyor: %s ta ariza %s · seed v%s (%s qator)",
            sum(all_s.values()),
            all_s,
            ORDERS_SEED_VERSION,
            len(ORDERS_SEED_ROWS),
        )
    except Exception:
        log.exception("DB holati log xato")
    try:
        active_rows = list_active_service_staff()
        for row in active_rows:
            uid = int(row.get("staff_id") or 0)
            if not uid:
                continue
            push_session_start_background(
                tg_id=uid,
                bot_key="ombor",
                user_name=row.get("staff_name") or "",
                activity_type="ombor",
                metadata={
                    "order_id": int(row.get("order_id") or 0),
                    "kind": row.get("kind_label") or "",
                },
            )
        if active_rows:
            log.info("Live hub sync: %s faol xizmat xodimi", len(active_rows))
        _reconcile_hub_live_sessions()
    except Exception:
        log.exception("ombor live hub sync xato")
    try:
        day = today_iso()
        st = stats_today()
        for row in st.get("by_staff", []):
            uid = int(row.get("staff_id") or 0)
            if not uid:
                continue
            summary = staff_today_hub_summary(uid, day)
            if "0 soniya" in summary and "0 ta" in summary:
                continue
            await push_to_yordamchi_hub(
                tg_id=uid,
                bot_key="ombor",
                summary=summary,
                day_iso=day,
            )
    except Exception:
        log.exception("ombor hub backfill xato")
    try:
        stats = collect_db_stats(DB_NAME)
        await bot.send_message(
            admin_notify_id(),
            format_startup_admin_message(stats),
            parse_mode="HTML",
        )
    except Exception:
        log.exception("Startup admin xabari yuborilmadi")
    if GROUP_ID is None:
        log.warning("GROUP_ID sozlanmagan")
    else:
        log.info("Guruh: %s", GROUP_ID)
        _ticker = LiveTicker(bot, GROUP_ID)
        _ticker.start()
    from telegram_polling_guard import ensure_polling_mode

    await ensure_polling_mode(bot)
    await dp.start_polling(bot)
    if _ticker:
        _ticker.stop()


if __name__ == "__main__":
    asyncio.run(main())
