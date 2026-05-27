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
        CREATE TABLE IF NOT EXISTS order_staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            staff_id INTEGER NOT NULL,
            staff_name TEXT NOT NULL,
            joined_at TEXT NOT NULL,
            is_lead INTEGER NOT NULL DEFAULT 0,
            UNIQUE(order_id, staff_id)
        )
    """)
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
    # Eski arizalar — bitta xodimni jamoaga ko'chirish
    conn.execute("""
        INSERT OR IGNORE INTO order_staff (order_id, staff_id, staff_name, joined_at, is_lead)
        SELECT id, assigned_to_id, assigned_to, COALESCE(assigned_at, created_at), 1
        FROM orders
        WHERE assigned_to_id IS NOT NULL AND assigned_to IS NOT NULL
    """)
    conn.commit()
    conn.close()


def get_order_staff(order_id: int) -> list[dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        """
        SELECT staff_id, staff_name, joined_at, is_lead
        FROM order_staff WHERE order_id=?
        ORDER BY is_lead DESC, joined_at ASC
        """,
        (order_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _staff_names(staff: list[dict[str, Any]], fallback: str | None = None) -> str | None:
    if staff:
        return ", ".join(s["staff_name"] for s in staff)
    return fallback


def attach_staff(order: dict[str, Any]) -> dict[str, Any]:
    out = dict(order)
    staff = get_order_staff(order["id"])
    out["staff"] = staff
    out["staff_ids"] = {s["staff_id"] for s in staff}
    out["staff_names"] = _staff_names(staff, order.get("assigned_to"))
    return out


def is_staff_on_order(order_id: int, staff_id: int) -> bool:
    conn = _conn()
    row = conn.execute(
        "SELECT 1 FROM order_staff WHERE order_id=? AND staff_id=?",
        (order_id, staff_id),
    ).fetchone()
    conn.close()
    return row is not None


def _add_staff_member(
    conn: sqlite3.Connection,
    order_id: int,
    staff_id: int,
    staff_name: str,
    *,
    is_lead: bool = False,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO order_staff (order_id, staff_id, staff_name, joined_at, is_lead)
        VALUES (?, ?, ?, ?, ?)
        """,
        (order_id, staff_id, staff_name, _now(), 1 if is_lead else 0),
    )


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
    if not row:
        return None
    return attach_staff(dict(row))


def staff_active_order(staff_id: int, except_order_id: int | None = None) -> dict[str, Any] | None:
    conn = _conn()
    if except_order_id:
        row = conn.execute(
            """
            SELECT o.* FROM orders o
            JOIN order_staff os ON os.order_id = o.id
            WHERE os.staff_id=? AND o.status='jarayonda' AND o.id != ?
            ORDER BY o.id DESC LIMIT 1
            """,
            (staff_id, except_order_id),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT o.* FROM orders o
            JOIN order_staff os ON os.order_id = o.id
            WHERE os.staff_id=? AND o.status='jarayonda'
            ORDER BY o.id DESC LIMIT 1
            """,
            (staff_id,),
        ).fetchone()
    conn.close()
    return attach_staff(dict(row)) if row else None


def assign_to_staff(
    order_id: int,
    staff_id: int,
    staff_name: str,
) -> tuple[dict[str, Any] | None, str | None]:
    order = get_order(order_id)
    if not order:
        return None, "Ariza topilmadi"
    if order["status"] != "yangi":
        if order["status"] == "jarayonda":
            return join_staff(order_id, staff_id, staff_name)
        return None, "Bu ariza allaqachon yopilgan"

    active = staff_active_order(staff_id, except_order_id=order_id)
    if active:
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
    _add_staff_member(conn, order_id, staff_id, staff_name, is_lead=True)
    conn.commit()
    row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    if not row or row["status"] != "jarayonda":
        return None, "Boshqa xodim oldin band qildi"
    return attach_staff(dict(row)), None


def join_staff(
    order_id: int,
    staff_id: int,
    staff_name: str,
) -> tuple[dict[str, Any] | None, str | None]:
    order = get_order(order_id)
    if not order:
        return None, "Ariza topilmadi"
    if order["status"] != "jarayonda":
        return None, "Bu ariza xizmatda emas"
    if is_staff_on_order(order_id, staff_id):
        return None, "Siz allaqachon bu jamoadasiz"

    active = staff_active_order(staff_id, except_order_id=order_id)
    if active:
        return None, f"Siz #{active['id']} da xizmat ko'rsatyapsiz — avval tugating"

    conn = _conn()
    _add_staff_member(conn, order_id, staff_id, staff_name, is_lead=False)
    conn.execute(
        "UPDATE orders SET updated_at=? WHERE id=?",
        (_now(), order_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    return attach_staff(dict(row)), None


def complete_order(
    order_id: int,
    staff_id: int,
) -> tuple[dict[str, Any] | None, str | None]:
    order = get_order(order_id)
    if not order:
        return None, "Ariza topilmadi"
    if order["status"] != "jarayonda":
        return None, "Bu ariza xizmatda emas"
    if not is_staff_on_order(order_id, staff_id):
        return None, "Avval «Qo'shilaman» yoki band qiling"

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
        WHERE id=? AND status='jarayonda'
        """,
        (now, secs, mins, now, order_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    if not row or row["status"] != "bajarildi":
        return None, "Tugatib bo'lmadi"
    return attach_staff(dict(row)), None


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
    return [attach_staff(dict(r)) for r in rows]
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
        SELECT os.staff_name AS assigned_to, COUNT(DISTINCT os.order_id) AS cnt,
               AVG(COALESCE(o.service_seconds, o.service_minutes * 60)) AS avg_sec,
               SUM(COALESCE(o.service_seconds, o.service_minutes * 60)) AS total_sec
        FROM order_staff os
        JOIN orders o ON o.id = os.order_id
        WHERE o.status='bajarildi' AND o.finished_at LIKE ?
        GROUP BY os.staff_id, os.staff_name
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
    return [attach_staff(dict(r)) for r in rows]


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
