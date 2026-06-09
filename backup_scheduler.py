"""Kunlik JSON zaxira — asyncio (qo'shimcha kutubxona shart emas)."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
TZ = ZoneInfo(os.getenv("TZ", "Asia/Tashkent"))


def _seconds_until(hour: int, minute: int) -> float:
    now = datetime.now(TZ)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def run_daily_backup(db_path: str, *, hour: int = 23, minute: int = 50) -> None:
    from db_backup import write_backup_files

    out = os.path.join(os.path.dirname(db_path) or ".", "backups")
    while True:
        await asyncio.sleep(_seconds_until(hour, minute))
        try:
            if os.path.isfile(db_path):
                write_backup_files(db_path, out)
                log.info("Kunlik auto-backup yozildi: %s", out)
        except Exception:
            log.exception("Kunlik auto-backup xato")
        await asyncio.sleep(60)
