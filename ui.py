"""Xabar formatlari."""

from __future__ import annotations

import os
from datetime import datetime
from datetime import timedelta
from html import escape

from storage import STATUSES, _parse_dt, seconds_between


def _e(text: str | None) -> str:
    return escape(text or "—")


TZ_OFFSET_HOURS = int((os.getenv("TZ_OFFSET_HOURS") or "5").strip() or "5")


def status_label(code: str) -> str:
    return STATUSES.get(code, code)


def _elapsed_seconds(since: str | None) -> int | None:
    start = _parse_dt(since)
    if not start:
        return None
    return max(0, int((datetime.now() - start).total_seconds()))


def _display_dt(raw: str | None, *, with_seconds: bool = True) -> str:
    dt = _parse_dt(raw)
    if not dt:
        return _e(raw)
    dt = dt + timedelta(hours=TZ_OFFSET_HOURS)
    fmt = "%Y-%m-%d %H:%M:%S" if with_seconds else "%Y-%m-%d %H:%M"
    return dt.strftime(fmt)


def _format_clock(total_sec: int) -> str:
    h, rem = divmod(total_sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_duration(order: dict) -> str:
    """Xizmat vaqtini o'qish — soniya aniq, daqiqa emas."""
    sec = order.get("service_seconds")
    if sec is None and order.get("service_minutes") is not None:
        sec = int(order["service_minutes"]) * 60
    if sec is None:
        sec = seconds_between(order.get("assigned_at"), order.get("finished_at"))
    if sec is None or sec < 0:
        return "—"
    if sec < 60:
        return f"{sec} soniya"
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    parts: list[str] = []
    if h:
        parts.append(f"{h} soat")
    if m:
        parts.append(f"{m} daqiqa")
    if s:
        parts.append(f"{s} soniya")
    return " ".join(parts) if parts else "0 soniya"


def live_timer_line(since: str | None, label: str) -> str:
    sec = _elapsed_seconds(since)
    if sec is None:
        return ""
    return f"🟢 LIVE  {label}: <b>{_format_clock(sec)}</b>"


def _elapsed_minutes(assigned_at: str | None) -> int | None:
    sec = _elapsed_seconds(assigned_at)
    if sec is None:
        return None
    return sec // 60


def welcome_card() -> str:
    return (
        "🏭 <b>OMBOR XIZMATI</b>\n\n"
        "Assalomu alaykum! Quyidagi tugmalardan tanlang 👇"
    )


def customer_sent(order_id: int) -> str:
    return f"✅  <b>#{order_id}</b> qabul qilindi.\nXodim tez orada javob beradi."


def customer_done(order: dict) -> str:
    staff = _e(order.get("staff_names") or order.get("assigned_to"))
    n = len(order.get("staff") or [])
    team = f" ({n} xodim)" if n > 1 else ""
    return (
        f"✅  <b>#{order['id']}</b> bajarildi\n"
        f"👷  {staff}{team}  ·  ⏱  {format_duration(order)}"
    )


def customer_rejected(order_id: int) -> str:
    return f"❌  <b>#{order_id}</b> rad etildi."


def order_card(order: dict, *, for_group: bool = False, live: bool = False) -> str:
    username = order.get("username")
    user_line = f"@{username}" if username else "—"
    status = status_label(order["status"])
    lines = [
        f"<b>{_e(order['kind_label'])}</b>  #{order['id']}",
        f"Holat: {status}",
    ]

    if live and for_group and order["status"] in ("yangi", "jarayonda"):
        lines.append("")
        if order["status"] == "yangi":
            wait = live_timer_line(order.get("created_at"), "⏳ Kutilyapti")
            if wait:
                lines.append(wait)
        elif order["status"] == "jarayonda":
            svc = live_timer_line(order.get("assigned_at"), "⏱ Xizmat vaqti")
            if svc:
                lines.append(svc)
            created = _parse_dt(order.get("created_at"))
            assigned = _parse_dt(order.get("assigned_at"))
            if created and assigned:
                queue_sec = max(0, int((assigned - created).total_seconds()))
                lines.append(f"⏳ Navbatda kutgan: <b>{_format_clock(queue_sec)}</b>")

    lines.extend([
        "",
        f"👤 Mijoz: {_e(order.get('full_name'))}",
        f"📱 {user_line}  ·  ID <code>{order['user_id']}</code>",
        f"🕐 Keldi: {_display_dt(order.get('created_at'))}",
    ])

    assignee = order.get("staff_names") or order.get("assigned_to")
    if assignee:
        n = len(order.get("staff") or [])
        label = "Jamoa" if n > 1 else "Xizmat ko'rsatyapti"
        lines.append(f"👷 {label}: <b>{_e(assignee)}</b>")
        if order["status"] == "jarayonda" and not live:
            elapsed = _elapsed_minutes(order.get("assigned_at"))
            if elapsed is not None:
                lines.append(f"⏱ Hozir: <b>{elapsed} daqiqa</b>")
        if order.get("assigned_at"):
            lines.append(f"🔗 Band qilindi: {_display_dt(order.get('assigned_at'), with_seconds=False)}")

    if order["status"] == "bajarildi":
        lines.append(f"⏱ Xizmat vaqti: <b>{format_duration(order)}</b>")
        if order.get("finished_at"):
            lines.append(f"✅ Tugadi: {_display_dt(order.get('finished_at'), with_seconds=False)}")

    lines.extend(["", _e(order.get("text"))])

    if for_group:
        if order["status"] == "yangi":
            lines.append("\n<i>👇 Bir xodim «Men xizmat ko'rsataman» deb band qilsin</i>")
        elif order["status"] == "jarayonda":
            lines.append("\n<i>👇 Boshqa xodimlar «Qo'shilaman» deb qo'shiladi</i>")

    return "\n".join(lines)


def user_orders_card(rows: list[dict]) -> str:
    if not rows:
        return "📋 Hali ariza yo'q.\n\nTugmalardan birini tanlang."
    lines = ["📋 <b>Sizning arizalaringiz</b>\n"]
    for r in rows:
        extra = ""
        if r["status"] == "jarayonda" and r.get("assigned_to"):
            extra = f"\n   👷 {_e(r['assigned_to'])} xizmat ko'rsatyapti"
        elif r["status"] == "bajarildi" and (
            r.get("service_seconds") is not None or r.get("service_minutes") is not None
        ):
            extra = f"\n   ⏱ {format_duration(r)} · 👷 {_e(r.get('assigned_to'))}"
        lines.append(
            f"#{r['id']}  {status_label(r['status'])}\n"
            f"   {_e(r['kind_label'])} · {_display_dt(r.get('created_at'), with_seconds=False)}{extra}"
        )
    return "\n".join(lines)


def notify_user_status(order: dict) -> str:
    lines = [
        f"🔔 <b>Ariza #{order['id']}</b>",
        f"Holat: {status_label(order['status'])}",
        f"{_e(order['kind_label'])}",
        "",
    ]
    if order.get("assigned_to"):
        lines.append(f"👷 Xodim: <b>{_e(order['assigned_to'])}</b>")
    if order["status"] == "jarayonda":
        lines.append("Xodim sizga xizmat ko'rsatmoqda...")
    if order["status"] == "bajarildi":
        lines.append(f"⏱ Xizmat vaqti: <b>{format_duration(order)}</b>")
        lines.append("Rahmat! Yana murojaat qiling.")
    elif order["status"] == "rad":
        lines.append("Ariza rad etildi. Qayta yuborishingiz mumkin.")
    else:
        lines.append("Savollar bo'lsa, ombor guruhiga murojaat qiling.")
    return "\n".join(lines)


def notify_staff_assigned(order: dict) -> str:
    return (
        f"✅ Siz #{order['id']} ni band qildingiz!\n"
        f"Mijoz: {_e(order.get('full_name'))}\n\n"
        "Xizmat tugagach guruhda «Xizmat tugadi» bosing."
    )


def notify_staff_completed(order: dict) -> str:
    return (
        f"✔️ #{order['id']} yakunlandi\n"
        f"⏱ Siz {format_duration(order)} xizmat ko'rsatdingiz."
    )


def service_done_group_card(order: dict) -> str:
    staff = _e(order.get("staff_names") or order.get("assigned_to"))
    n = len(order.get("staff") or [])
    team_line = f" ({n} kishi)" if n > 1 else ""
    return (
        f"✅ <b>XIZMAT YAKUNLANDI</b>  #{order['id']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👷 Jamoa{team_line}: <b>{staff}</b>\n"
        f"⏱ Vaqt: <b>{format_duration(order)}</b>\n"
        f"👤 Mijoz: {_e(order.get('full_name'))}\n"
        f"📦 {_e(order.get('kind_label'))}"
    )


def prompt_for_type(request_type: str) -> str:
    prompts = {
        "product_order": (
            "📦 <b>Tovar buyurtma</b>\n\n"
            "Ro'yxatni yozing:\n"
            "<i>Masalan:</i>\n"
            "1. Cola 1L — 12 dona\n"
            "2. Pechenye — 4 quti\n\n"
            "Faqat matn yuboring."
        ),
        "info": (
            "ℹ️ <b>Savol / ma'lumot</b>\n\n"
            "Savolingizni yozing — javob beramiz."
        ),
    }
    return prompts.get(request_type, "Matn yuboring:")


def instant_confirm_text(request_type: str) -> str:
    texts = {
        "call_staff": (
            "🙋 <b>Iltimos, menga xizmat ko'rsating</b>\n\n"
            "Tez chaqiruv yuborilsinmi?\n"
            "Ombor guruhiga xabar boradi."
        ),
        "check_client": (
            "👀 <b>Iltimos, ombordagi mijozga qarang</b>\n\n"
            "Tez chaqiruv yuborilsinmi?\n"
            "Ombor guruhiga xabar boradi."
        ),
    }
    return texts.get(request_type, "Yuborilsinmi?")


def instant_order_text(request_type: str) -> str:
    texts = {
        "call_staff": "🙋 Iltimos, menga xizmat ko'rsating!",
        "check_client": "👀 Iltimos, ombordagi mijozga qarang!",
    }
    return texts.get(request_type, "Tez so'rov")


def report_today_card(stats: dict) -> str:
    lines = [
        "📊 <b>Bugungi hisobot</b>",
        f"📅 {stats['date']}",
        "━━━━━━━━━━━━━━━━━━",
        f"Jami bugun: <b>{stats['total_today']}</b>",
        f"Hozir xizmatda: <b>{stats['active_now']}</b>",
        "",
        "<b>Holat bo'yicha:</b>",
    ]
    if stats["by_status"]:
        for code, cnt in stats["by_status"].items():
            lines.append(f"  {status_label(code)} — {cnt}")
    else:
        lines.append("  Bugun ariza yo'q")
    lines.append("\n<b>👷 Xodimlar (bugun bajarilgan):</b>")
    if stats["by_staff"]:
        for s in stats["by_staff"]:
            avg = int(s["avg_sec"] or 0)
            total = int(s["total_sec"] or 0)
            lines.append(
                f"  <b>{_e(s['assigned_to'])}</b> — {s['cnt']} ta, "
                f"o'rtacha {_format_clock(avg)}, jami {_format_clock(total)}"
            )
    else:
        lines.append("  Hali yakunlangan xizmat yo'q")
    return "\n".join(lines)


def report_staff_card(stats: dict) -> str:
    lines = [
        "👷 <b>Xodimlar hisoboti</b>",
        f"📅 {stats['date']}",
        "━━━━━━━━━━━━━━━━━━",
    ]
    if not stats["by_staff"]:
        lines.append("Bugun yakunlangan xizmat yo'q.")
        return "\n".join(lines)
    for i, s in enumerate(stats["by_staff"], 1):
        avg = int(s["avg_sec"] or 0)
        total = int(s["total_sec"] or 0)
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        lines.append(
            f"{medal} <b>{_e(s['assigned_to'])}</b>\n"
            f"   Xizmatlar: {s['cnt']} ta\n"
            f"   O'rtacha: {_format_clock(avg)}\n"
            f"   Jami vaqt: {_format_clock(total)}\n"
        )
    return "\n".join(lines)


def report_all_card(by_status: dict, recent: list[dict]) -> str:
    lines = [
        "📈 <b>Umumiy holat hisoboti</b>",
        "━━━━━━━━━━━━━━━━━━",
        "<b>Barcha arizalar (holat):</b>",
    ]
    total = sum(by_status.values())
    for code in ("yangi", "jarayonda", "bajarildi", "rad"):
        cnt = by_status.get(code, 0)
        if cnt:
            lines.append(f"  {status_label(code)} — {cnt}")
    lines.append(f"\n<b>Jami:</b> {total}")
    if recent:
        lines.append("\n<b>Oxirgi arizalar:</b>")
        for r in recent[:8]:
            staff = f" · 👷 {_e(r['assigned_to'])}" if r.get("assigned_to") else ""
            dur = f" · ⏱ {format_duration(r)}" if (
                r.get("service_seconds") is not None or r.get("service_minutes") is not None
            ) else ""
            lines.append(
                f"#{r['id']} {status_label(r['status'])}{staff}{dur}\n"
                f"   {_e(r['full_name'])} · {_e(r['kind_label'])}"
            )
    return "\n".join(lines)
