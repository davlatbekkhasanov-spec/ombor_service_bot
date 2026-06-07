"""Deploydan keyin orders_seed ni SQLite ga tiklash."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

log = logging.getLogger(__name__)


def _ensure_meta(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orders_seed_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            version INTEGER NOT NULL,
            applied_at TEXT NOT NULL,
            note TEXT
        )
        """
    )


def _order_exists(conn: sqlite3.Connection, row: dict[str, Any]) -> bool:
    fin = row.get("finished_at")
    lead = row.get("assigned_to_id")
    if not fin or not lead:
        return False
    hit = conn.execute(
        """
        SELECT 1 FROM orders o
        JOIN order_staff os ON os.order_id = o.id AND os.is_lead = 1
        WHERE o.finished_at = ? AND os.staff_id = ? AND o.kind_label = ?
        LIMIT 1
        """,
        (fin, lead, row.get("kind_label")),
    ).fetchone()
    return hit is not None


def _insert_seed_order(conn: sqlite3.Connection, row: dict[str, Any]) -> int | None:
    cols = (
        "user_id",
        "username",
        "full_name",
        "request_type",
        "kind_label",
        "text",
        "status",
        "created_at",
        "updated_at",
        "assigned_to",
        "assigned_to_id",
        "assigned_at",
        "finished_at",
        "service_minutes",
        "service_seconds",
    )
    values = [row.get(c) for c in cols]
    placeholders = ",".join("?" for _ in cols)
    conn.execute(
        f"INSERT INTO orders ({','.join(cols)}) VALUES ({placeholders})",
        values,
    )
    order_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    for i, member in enumerate(row.get("staff") or []):
        conn.execute(
            """
            INSERT OR IGNORE INTO order_staff
                (order_id, staff_id, staff_name, joined_at, is_lead)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                order_id,
                member["staff_id"],
                member["staff_name"],
                row.get("assigned_at") or row.get("created_at"),
                1 if i == 0 or member.get("is_lead") else 0,
            ),
        )
    return order_id


def _bump_sequence(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT MAX(id) FROM orders").fetchone()
    max_id = int(row[0] or 0)
    if max_id <= 0:
        return
    conn.execute(
        "UPDATE sqlite_sequence SET seq = ? WHERE name = 'orders'",
        (max_id,),
    )


def ensure_orders_seed(conn: sqlite3.Connection | None = None) -> int:
    """Yo'q arizalarni orders_seed dan qo'shadi. Qo'shilganlar soni."""
    from orders_seed import ORDERS_SEED_NOTE, ORDERS_SEED_ROWS, ORDERS_SEED_VERSION

    own = conn is None
    if own:
        from storage import _conn

        conn = _conn()
    assert conn is not None

    _ensure_meta(conn)
    added = 0
    for row in ORDERS_SEED_ROWS:
        if _order_exists(conn, row):
            continue
        if _insert_seed_order(conn, row):
            added += 1

    if added:
        _bump_sequence(conn)
        log.info("orders_seed: %s ta ariza tiklandi (%s)", added, ORDERS_SEED_NOTE)

    meta = conn.execute("SELECT version FROM orders_seed_meta WHERE id = 1").fetchone()
    applied_ver = int(meta[0]) if meta else 0
    if added or applied_ver < ORDERS_SEED_VERSION:
        from storage import _now

        conn.execute(
            """
            INSERT INTO orders_seed_meta(id, version, applied_at, note)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                version = excluded.version,
                applied_at = excluded.applied_at,
                note = excluded.note
            """,
            (ORDERS_SEED_VERSION, _now(), ORDERS_SEED_NOTE),
        )

    if own:
        conn.commit()
        conn.close()
    return added
