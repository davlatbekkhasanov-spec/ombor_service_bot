"""SQLite — arizalar va hisobotlar."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

DB_NAME = "orders.db"

STATUSES = {
    "yangi": "🆕 Yangi",
    "qabul": "✅ Qabul qilindi",
    "jarayonda": "🔄 Jarayonda",
    "bajarildi": "✔️ Bajarildi",
    "rad": "❌ Rad etildi",
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            full_name TEXT,
            request_type TEXT NOT NULL,
            kind_label TEXT NOT NULL,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'yangi',
            created_at TEXT NOT NULL,
            updated_at TEXT,
            accepted_by TEXT,
            accepted_by_id INTEGER,
            group_message_id INTEGER
        )
    """)
    for col, ddl in (
        ("request_type", "TEXT DEFAULT 'product_order'"),
        ("kind_label", "TEXT DEFAULT ''"),
        ("updated_at", "TEXT"),
        ("accepted_by", "TEXT"),
        ("accepted_by_id", "INTEGER"),
        ("group_message_id", "INTEGER"),
    ):
        try:
            conn.execute(f"ALTER TABLE orders ADD COLUMN {col} {ddl}")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def create_order(
    *,
    user_id: int,
    username: str | None,
    full_name: str | None,
    request_type: str,
    kind_label: str,
    text: str,
) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO orders
            (user_id, username, full_name, request_type, kind_label, text, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'yangi', ?, ?)
        """,
        (user_id, username, full_name, request_type, kind_label, text, now, now),
    )
    order_id = cur.lastrowid
    conn.commit()
    conn.close()
    return int(order_id)


def get_order(order_id: int) -> dict[str, Any] | None:
    conn = _conn()
    row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_group_message(order_id: int, message_id: int) -> None:
    conn = _conn()
    conn.execute(
        "UPDATE orders SET group_message_id=? WHERE id=?",
        (message_id, order_id),
    )
    conn.commit()
    conn.close()


def update_status(
    order_id: int,
    status: str,
    *,
    actor_name: str | None = None,
    actor_id: int | None = None,
) -> dict[str, Any] | None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = _conn()
    conn.execute(
        """
        UPDATE orders
        SET status=?, updated_at=?, accepted_by=COALESCE(?, accepted_by),
            accepted_by_id=COALESCE(?, accepted_by_id)
        WHERE id=?
        """,
        (status, now, actor_name, actor_id, order_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def user_orders(user_id: int, limit: int = 8) -> list[dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        """
        SELECT id, kind_label, status, created_at, updated_at
        FROM orders WHERE user_id=? ORDER BY id DESC LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def recent_orders(limit: int = 15) -> list[dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        """
        SELECT id, full_name, kind_label, status, created_at, text
        FROM orders ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def stats_today() -> dict[str, Any]:
    today = datetime.now().strftime("%Y-%m-%d")
    conn = _conn()
    by_status = conn.execute(
        """
        SELECT status, COUNT(*) AS cnt FROM orders
        WHERE created_at LIKE ? GROUP BY status
        """,
        (f"{today}%",),
    ).fetchall()
    by_type = conn.execute(
        """
        SELECT kind_label, COUNT(*) AS cnt FROM orders
        WHERE created_at LIKE ? GROUP BY kind_label
        ORDER BY cnt DESC
        """,
        (f"{today}%",),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE created_at LIKE ?",
        (f"{today}%",),
    ).fetchone()[0]
    all_total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    conn.close()
    return {
        "date": today,
        "total_today": total,
        "total_all": all_total,
        "by_status": {r["status"]: r["cnt"] for r in by_status},
        "by_type": [(r["kind_label"], r["cnt"]) for r in by_type],
    }


def stats_all_status() -> dict[str, int]:
    conn = _conn()
    rows = conn.execute(
        "SELECT status, COUNT(*) AS cnt FROM orders GROUP BY status"
    ).fetchall()
    conn.close()
    return {r["status"]: r["cnt"] for r in rows}
