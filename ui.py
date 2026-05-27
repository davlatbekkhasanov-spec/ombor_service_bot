"""Xabar formatlari."""

from __future__ import annotations

from html import escape

from storage import STATUSES


def _e(text: str | None) -> str:
    return escape(text or "—")


def status_label(code: str) -> str:
    return STATUSES.get(code, code)


def welcome_card() -> str:
    return (
        "🏭 <b>OMBOR XIZMATI</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Assalomu alaykum!\n\n"
        "Ombor xodimlari va mijozlar uchun tez yordam boti.\n"
        "Quyidagi tugmalardan birini tanlang:\n\n"
        "🙋 <b>Xizmat ko'rsating</b> — tez chaqiruv\n"
        "👀 <b>Mijozga qarang</b> — ombordagi mijoz\n"
        "📦 <b>Buyurtma</b> — tovar ro'yxati\n"
        "📋 <b>Olib keling</b> — mahsulot yetkazish\n"
        "⭐ <b>VIP</b> — shoshilinch\n"
        "⚠️ <b>Muammo</b> — shikoyat\n"
        "ℹ️ <b>Savol</b> — ma'lumot"
    )


def order_card(order: dict, *, for_group: bool = False) -> str:
    username = order.get("username")
    user_line = f"@{username}" if username else "—"
    status = status_label(order["status"])
    lines = [
        f"<b>{_e(order['kind_label'])}</b>  #{order['id']}",
        f"Holat: {status}",
        "",
        f"👤 {_e(order.get('full_name'))}",
        f"📱 {user_line}  ·  ID <code>{order['user_id']}</code>",
        f"🕐 {_e(order.get('created_at'))}",
    ]
    if order.get("accepted_by"):
        lines.append(f"👷 Javobgar: {_e(order['accepted_by'])}")
    if order.get("updated_at") and order.get("updated_at") != order.get("created_at"):
        lines.append(f"🔄 Yangilandi: {_e(order['updated_at'])}")
    lines.extend(["", _e(order.get("text"))])
    if for_group and order["status"] == "yangi":
        lines.append("\n<i>👇 Qabul qiling yoki rad eting</i>")
    return "\n".join(lines)


def user_orders_card(rows: list[dict]) -> str:
    if not rows:
        return "📋 Hali ariza yo'q.\n\nTugmalardan birini tanlang."
    lines = ["📋 <b>Sizning arizalaringiz</b>\n"]
    for r in rows:
        lines.append(
            f"#{r['id']}  {status_label(r['status'])}\n"
            f"   {_e(r['kind_label'])} · {_e(r['created_at'])}"
        )
    return "\n".join(lines)


def notify_user_status(order: dict) -> str:
    return (
        f"🔔 <b>Ariza #{order['id']}</b>\n"
        f"Holat: {status_label(order['status'])}\n"
        f"{_e(order['kind_label'])}\n\n"
        + (f"👷 {_e(order.get('accepted_by'))}\n\n" if order.get("accepted_by") else "")
        + "Savollar bo'lsa, ombor guruhiga murojaat qiling."
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
        "bring_product": (
            "📋 <b>Mahsulot olib keling</b>\n\n"
            "Qaysi mahsulot, qayerdan va qayerga kerakligini yozing."
        ),
        "vip": (
            "⭐ <b>VIP / Shoshilinch</b>\n\n"
            "Mijoz, bo'lim va tavarlar — qisqa va aniq yozing."
        ),
        "complaint": (
            "⚠️ <b>Muammo / shikoyat</b>\n\n"
            "Nima bo'lganini batafsil yozing."
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
        f"📊 <b>Bugungi hisobot</b>",
        f"📅 {stats['date']}",
        "━━━━━━━━━━━━━━━━━━",
        f"Jami bugun: <b>{stats['total_today']}</b>",
        f"Umumiy bazada: <b>{stats['total_all']}</b>",
        "",
        "<b>Holat bo'yicha:</b>",
    ]
    if stats["by_status"]:
        for code, cnt in stats["by_status"].items():
            lines.append(f"  {status_label(code)} — {cnt}")
    else:
        lines.append("  Bugun ariza yo'q")
    lines.append("\n<b>Turi bo'yicha:</b>")
    if stats["by_type"]:
        for label, cnt in stats["by_type"]:
            lines.append(f"  {_e(label)} — {cnt}")
    else:
        lines.append("  —")
    return "\n".join(lines)


def report_all_card(by_status: dict, recent: list[dict]) -> str:
    lines = [
        "📈 <b>Umumiy holat hisoboti</b>",
        "━━━━━━━━━━━━━━━━━━",
        "<b>Barcha arizalar (holat):</b>",
    ]
    total = sum(by_status.values())
    for code in ("yangi", "qabul", "jarayonda", "bajarildi", "rad"):
        cnt = by_status.get(code, 0)
        if cnt:
            lines.append(f"  {status_label(code)} — {cnt}")
    lines.append(f"\n<b>Jami:</b> {total}")
    if recent:
        lines.append("\n<b>Oxirgi arizalar:</b>")
        for r in recent[:8]:
            lines.append(
                f"#{r['id']} {status_label(r['status'])} · {_e(r['kind_label'])}\n"
                f"   {_e(r['full_name'])} · {_e(r['created_at'])}"
            )
    return "\n".join(lines)
