"""SQLite — arizalar va hisobotlar."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

DB_NAME = "orders.db"

STATUSES = {
    "yangi": "🆕 Yangi",
    "jarayonda": "🔄 Xizmatda",
    "bajarildi": "✔️ Bajarildi",
    "rad": "❌ Rad etildi",
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def minutes_between(start: str | None, end: str | None) -> int | None:
    sec = seconds_between(start, end)
    if sec is None:
        return None
    return sec // 60


def seconds_between(start: str | None, end: str | None) -> int | None:
    s, e = _parse_dt(start), _parse_dt(end)
    if not s or not e:
        return None
    return max(0, int((e - s).total_seconds()))


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
            assigned_to TEXT,
            assigned_to_id INTEGER,
            assigned_at TEXT,
            finished_at TEXT,
            service_minutes INTEGER,
            service_seconds INTEGER,
            group_message_id INTEGER
        )
    """)
    for col, ddl in (
        ("request_type", "TEXT DEFAULT 'product_order'"),
        ("kind_label", "TEXT DEFAULT ''"),
        ("updated_at", "TEXT"),
        ("assigned_to", "TEXT"),
        ("assigned_to_id", "INTEGER"),
        ("assigned_at", "TEXT"),
        ("finished_at", "TEXT"),
        ("service_minutes", "INTEGER"),
        ("service_seconds", "INTEGER"),
        ("group_message_id", "INTEGER"),
        ("accepted_by", "TEXT"),
        ("accepted_by_id", "INTEGER"),
    ):
        try:
            conn.execute(f"ALTER TABLE orders ADD COLUMN {col} {ddl}")
        except sqlite3.OperationalError:
            pass
    conn.execute("""
        UPDATE orders SET assigned_to = accepted_by
        WHERE assigned_to IS NULL AND accepted_by IS NOT NULL
    """)
    conn.execute("""
        UPDATE orders SET assigned_to_id = accepted_by_id
        WHERE assigned_to_id IS NULL AND accepted_by_id IS NOT NULL
    """)
    conn.execute("""
        UPDATE orders SET status = 'jarayonda'
        WHERE status = 'qabul'
    """)
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
    now = _now()
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


def staff_active_order(staff_id: int) -> dict[str, Any] | None:
    conn = _conn()
    row = conn.execute(
        """
        SELECT * FROM orders
        WHERE assigned_to_id=? AND status='jarayonda'
        ORDER BY id DESC LIMIT 1
        """,
        (staff_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def assign_to_staff(
    order_id: int,
    staff_id: int,
    staff_name: str,
) -> tuple[dict[str, Any] | None, str | None]:
    order = get_order(order_id)
    if not order:
        return None, "Ariza topilmadi"
    if order["status"] != "yangi":
        if order.get("assigned_to"):
            return None, f"Bu arizani {order['assigned_to']} band qilgan"
        return None, "Bu ariza allaqachon yopilgan yoki band"

    active = staff_active_order(staff_id)
    if active and active["id"] != order_id:
        return None, f"Siz #{active['id']} da xizmat ko'rsatyapsiz — avval tugating"

    now = _now()
    conn = _conn()
    conn.execute(
        """
        UPDATE orders
        SET status='jarayonda', assigned_to=?, assigned_to_id=?,
            assigned_at=?, updated_at=?
        WHERE id=? AND status='yangi'
        """,
        (staff_name, staff_id, now, now, order_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    if not row:
        return None, "Boshqa xodim oldin band qildi"
    return dict(row), None


def complete_order(
    order_id: int,
    staff_id: int,
) -> tuple[dict[str, Any] | None, str | None]:
    order = get_order(order_id)
    if not order:
        return None, "Ariza topilmadi"
    if order["status"] != "jarayonda":
        return None, "Bu ariza xizmatda emas"
    if order.get("assigned_to_id") and order["assigned_to_id"] != staff_id:
        return None, f"Faqat {order.get('assigned_to')} tugatishi mumkin"

    now = _now()
    start_at = order.get("assigned_at") or order.get("created_at")
    secs = seconds_between(start_at, now)
    if secs is None:
        secs = 0
    if order.get("assigned_at") and secs == 0:
        secs = 1
    mins = max(1, (secs + 59) // 60) if secs > 0 else 0
    conn = _conn()
    conn.execute(
        """
        UPDATE orders
        SET status='bajarildi', finished_at=?, service_seconds=?, service_minutes=?, updated_at=?
        WHERE id=? AND status='jarayonda' AND assigned_to_id=?
        """,
        (now, secs, mins, now, order_id, staff_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    if not row or row["status"] != "bajarildi":
        return None, "Tugatib bo'lmadi"
    return dict(row), None


def reject_order(order_id: int) -> dict[str, Any] | None:
    order = get_order(order_id)
    if not order or order["status"] != "yangi":
        return None
    now = _now()
    conn = _conn()
    conn.execute(
        "UPDATE orders SET status='rad', updated_at=? WHERE id=? AND status='yangi'",
        (now, order_id),
    )
    conn.commit()
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


def user_orders(user_id: int, limit: int = 8) -> list[dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        """
        SELECT id, kind_label, status, created_at, assigned_to, service_minutes, service_seconds
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
        SELECT id, full_name, kind_label, status, created_at, text,
               assigned_to, service_minutes, service_seconds
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
    by_staff = conn.execute(
        """
        SELECT assigned_to, COUNT(*) AS cnt,
               AVG(COALESCE(service_seconds, service_minutes * 60)) AS avg_sec,
               SUM(COALESCE(service_seconds, service_minutes * 60)) AS total_sec
        FROM orders
        WHERE status='bajarildi' AND finished_at LIKE ? AND assigned_to IS NOT NULL
        GROUP BY assigned_to_id, assigned_to
        ORDER BY cnt DESC
        """,
        (f"{today}%",),
    ).fetchall()
    active = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE status='jarayonda'"
    ).fetchone()[0]
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
        "active_now": active,
        "by_status": {r["status"]: r["cnt"] for r in by_status},
        "by_type": [(r["kind_label"], r["cnt"]) for r in by_type],
        "by_staff": [dict(r) for r in by_staff],
    }


def stats_all_status() -> dict[str, int]:
    conn = _conn()
    rows = conn.execute(
        "SELECT status, COUNT(*) AS cnt FROM orders GROUP BY status"
    ).fetchall()
    conn.close()
    return {r["status"]: r["cnt"] for r in rows}


def live_orders() -> list[dict[str, Any]]:
    """Yangi va xizmatdagi — LIVE taymer yangilanadigan arizalar."""
    conn = _conn()
    rows = conn.execute(
        """
        SELECT * FROM orders
        WHERE status IN ('yangi', 'jarayonda')
          AND group_message_id IS NOT NULL
        ORDER BY id ASC
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def any_live_orders() -> bool:
    conn = _conn()
    n = conn.execute(
        """
        SELECT COUNT(*) FROM orders
        WHERE status IN ('yangi', 'jarayonda') AND group_message_id IS NOT NULL
        """
    ).fetchone()[0]
    conn.close()
    return n > 0
