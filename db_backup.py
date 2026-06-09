"""SQLite backup/export/restore — deploy oldin zaxira va qo'lda tiklash."""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.getenv("TZ", "Asia/Tashkent"))

TABLES = (
    "orders",
    "order_staff",
    "orders_seed_meta",
)


def _now_stamp() -> str:
    return datetime.now(TZ).strftime("%Y%m%d_%H%M%S")


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    try:
        cur = conn.execute(f"SELECT * FROM {table} ORDER BY rowid")
        return [dict(r) for r in cur.fetchall()]
    except sqlite3.OperationalError:
        return []


def export_payload(db_path: str) -> dict:
    conn = _connect(db_path)
    try:
        payload = {
            "exported_at": datetime.now(TZ).isoformat(timespec="seconds"),
            "db_path": db_path,
            "bot": "ombor_service_bot",
            "tables": {},
        }
        for table in TABLES:
            payload["tables"][table] = _rows(conn, table)
        payload["counts"] = {t: len(payload["tables"][t]) for t in TABLES}
        return payload
    finally:
        conn.close()


def payload_to_json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def payload_to_orders_csv(payload: dict) -> bytes:
    rows = payload.get("tables", {}).get("orders", [])
    buf = io.StringIO()
    if not rows:
        w = csv.writer(buf)
        w.writerow(["id"])
        return buf.getvalue().encode("utf-8-sig")
    fields = list(rows[0].keys())
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8-sig")


def write_backup_files(db_path: str, out_dir: str) -> dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    stamp = _now_stamp()
    payload = export_payload(db_path)
    files: dict[str, str] = {}

    json_path = os.path.join(out_dir, f"backup_{stamp}.json")
    with open(json_path, "wb") as f:
        f.write(payload_to_json_bytes(payload))
    files["json"] = json_path

    orders_csv = os.path.join(out_dir, f"orders_{stamp}.csv")
    with open(orders_csv, "wb") as f:
        f.write(payload_to_orders_csv(payload))
    files["orders_csv"] = orders_csv

    if os.path.isfile(db_path):
        db_copy = os.path.join(out_dir, f"orders_{stamp}.db")
        shutil.copy2(db_path, db_copy)
        files["db_copy"] = db_copy

    return files


def restore_all_from_json(db_path: str, backup_json_path: str, *, replace: bool = False) -> dict:
    with open(backup_json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    tables = payload.get("tables", {})
    orders = tables.get("orders", [])
    staff = tables.get("order_staff", [])
    meta = tables.get("orders_seed_meta", [])
    if not orders:
        return {"ok": False, "message": "orders bo'sh", "orders": 0, "staff": 0}

    conn = _connect(db_path)
    try:
        if replace:
            conn.execute("DELETE FROM order_staff")
            conn.execute("DELETE FROM orders")
            conn.execute("DELETE FROM orders_seed_meta")
        order_n = 0
        for r in orders:
            cols = list(r.keys())
            placeholders = ",".join("?" for _ in cols)
            conn.execute(
                f"INSERT INTO orders ({','.join(cols)}) VALUES ({placeholders})",
                [r[c] for c in cols],
            )
            order_n += 1
        staff_n = 0
        for r in staff:
            cols = list(r.keys())
            placeholders = ",".join("?" for _ in cols)
            conn.execute(
                f"INSERT INTO order_staff ({','.join(cols)}) VALUES ({placeholders})",
                [r[c] for c in cols],
            )
            staff_n += 1
        row = conn.execute("SELECT MAX(id) FROM orders").fetchone()
        max_id = int(row[0] or 0)
        if max_id > 0:
            conn.execute(
                "UPDATE sqlite_sequence SET seq = ? WHERE name = 'orders'",
                (max_id,),
            )
        if meta:
            conn.execute("DELETE FROM orders_seed_meta")
            for r in meta:
                conn.execute(
                    """
                    INSERT INTO orders_seed_meta(id, version, applied_at, note)
                    VALUES (?, ?, ?, ?)
                    """,
                    (r.get("id", 1), r["version"], r["applied_at"], r.get("note")),
                )
        conn.commit()
        return {
            "ok": True,
            "replace": replace,
            "orders": order_n,
            "staff": staff_n,
            "counts_source": payload.get("counts", {}),
        }
    finally:
        conn.close()
