"""SQLite dan orders_seed.py yangilash (Railway shell yoki lokal DB)."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DB = os.getenv("DB_PATH", "/data/orders.db").strip() or "/data/orders.db"


def export_rows(conn: sqlite3.Connection) -> list[dict]:
    conn.row_factory = sqlite3.Row
    orders = conn.execute(
        """
        SELECT * FROM orders
        WHERE status = 'bajarildi' AND finished_at IS NOT NULL
        ORDER BY finished_at ASC, id ASC
        """
    ).fetchall()
    out: list[dict] = []
    for o in orders:
        staff = conn.execute(
            """
            SELECT staff_id, staff_name, is_lead
            FROM order_staff WHERE order_id=?
            ORDER BY is_lead DESC, joined_at ASC
            """,
            (o["id"],),
        ).fetchall()
        if not staff:
            continue
        out.append(
            {
                "id": o["id"],
                "user_id": o["user_id"],
                "username": o["username"],
                "full_name": o["full_name"],
                "request_type": o["request_type"],
                "kind_label": o["kind_label"],
                "text": (o["text"] or "")[:500],
                "status": o["status"],
                "created_at": o["created_at"],
                "updated_at": o["updated_at"],
                "assigned_to": o["assigned_to"],
                "assigned_to_id": o["assigned_to_id"],
                "assigned_at": o["assigned_at"],
                "finished_at": o["finished_at"],
                "service_seconds": o["service_seconds"],
                "service_minutes": o["service_minutes"],
                "staff": [
                    {
                        "staff_id": s["staff_id"],
                        "staff_name": s["staff_name"],
                        "is_lead": bool(s["is_lead"]),
                    }
                    for s in staff
                ],
            }
        )
    return out


def main() -> int:
    if not Path(DB).is_file():
        print(f"DB topilmadi: {DB}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(DB)
    rows = export_rows(conn)
    conn.close()
    from tools.build_orders_seed import render_py

    ver = int(os.getenv("ORDERS_SEED_VERSION", "2"))
    note = os.getenv("ORDERS_SEED_NOTE", f"export {DB}")
    out = ROOT / "orders_seed.py"
    out.write_text(render_py(rows, version=ver, note=note), encoding="utf-8")
    print(f"Exported {len(rows)} orders -> {out}")
    print(json.dumps({"orders": len(rows), "db": DB}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
