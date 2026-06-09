"""Deploydan keyin bo'sh DB ni startup zaxira yoki seed dan tiklash."""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3

log = logging.getLogger(__name__)

MIN_ORDERS_FOR_OK = 15
MIN_DB_BYTES_FOR_OK = 24 * 1024


def _order_count(db_path: str) -> int:
    if not os.path.isfile(db_path):
        return 0
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) FROM orders").fetchone()
        return int(row[0] or 0)
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def _needs_restore(db_path: str) -> bool:
    n = _order_count(db_path)
    if n >= MIN_ORDERS_FOR_OK:
        return False
    if os.path.isfile(db_path) and os.path.getsize(db_path) >= MIN_DB_BYTES_FOR_OK and n >= 5:
        return False
    return True


def _latest_startup_backup(db_path: str) -> str | None:
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(db_path)), "backups")
    if not os.path.isdir(backup_dir):
        return None
    try:
        names = sorted(
            (n for n in os.listdir(backup_dir) if n.startswith("startup_") and n.endswith(".db")),
            reverse=True,
        )
    except OSError:
        return None
    for name in names:
        full = os.path.join(backup_dir, name)
        if os.path.isfile(full) and os.path.getsize(full) > MIN_DB_BYTES_FOR_OK:
            return full
    return None


def ensure_baseline_restored(db_path: str) -> dict:
    """DB juda bo'sh bo'lsa — oxirgi startup zaxira yoki orders_seed."""
    before = _order_count(db_path)
    if not _needs_restore(db_path):
        return {"ok": True, "skipped": True, "orders": before}

    latest = _latest_startup_backup(db_path)
    if latest:
        try:
            shutil.copy2(latest, db_path)
            after = _order_count(db_path)
            log.warning("Startup zaxiradan tiklandi: %s -> %s ariza", before, after)
            return {
                "ok": True,
                "restored": True,
                "source": "startup_backup",
                "from": latest,
                "before": before,
                "after": after,
            }
        except OSError as exc:
            log.error("Startup zaxira tiklash xato: %s", exc)

    from orders_persist import ensure_orders_seed

    added = ensure_orders_seed()
    after = _order_count(db_path)
    if after > before:
        log.warning("orders_seed tiklandi: %s -> %s ariza (+%s)", before, after, added)
        return {
            "ok": True,
            "restored": True,
            "source": "orders_seed",
            "before": before,
            "after": after,
            "seed_added": added,
        }
    return {"ok": True, "skipped": True, "orders": after, "reason": "zaxira topilmadi"}
