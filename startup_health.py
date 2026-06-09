"""Ishga tushganda admin uchun qisqa holat."""

from __future__ import annotations

import os
import sqlite3
from typing import Any

from persist_data import has_railway_volume, persistence_status_line


def collect_db_stats(db_path: str) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "db_path": db_path,
        "size_kb": 0,
        "orders": 0,
        "done": 0,
        "volume": has_railway_volume(),
        "mount": os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "") or "—",
    }
    if not os.path.isfile(db_path):
        return stats
    stats["size_kb"] = os.path.getsize(db_path) // 1024
    try:
        conn = sqlite3.connect(db_path)
        stats["orders"] = int(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] or 0)
        stats["done"] = int(
            conn.execute("SELECT COUNT(*) FROM orders WHERE status='bajarildi'").fetchone()[0] or 0
        )
        conn.close()
    except sqlite3.Error as exc:
        stats["error"] = str(exc)
    return stats


def format_startup_admin_message(stats: dict) -> str:
    vol = "✅" if stats.get("volume") else "❌"
    lines = [
        "🚀 <b>Ombor bot ishga tushdi</b>",
        "",
        f"💾 {html_esc(persistence_status_line(stats.get('db_path', '')))}",
        f"📋 Arizalar: <b>{stats.get('orders', 0)}</b> · bajarildi <b>{stats.get('done', 0)}</b>",
        f"📦 Volume: {vol} ({html_esc(str(stats.get('mount', '—')))})",
    ]
    if not stats.get("volume"):
        lines.extend(["", "⚠️ Volume yo'q — /data mount qiling!"])
    elif int(stats.get("orders") or 0) < 5:
        lines.extend(["", "⚠️ DB kam — seed yoki backup kerak bo'lishi mumkin"])
    else:
        lines.extend(["", "✅ Ma'lumotlar joyida."])
    lines.append("")
    lines.append("Hub: har tugatishda kunlik jami yuboriladi.")
    return "\n".join(lines)


def html_esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
