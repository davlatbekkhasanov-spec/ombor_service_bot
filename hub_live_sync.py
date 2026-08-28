"""Jonli hub sessiyalarini DB holati bilan moslashtirish."""

from __future__ import annotations

import json
import logging
import urllib.request

from storage import list_active_service_staff
from yordamchi_push import HUB_SECRET, HUB_URL, push_session_end_background

log = logging.getLogger(__name__)


def reconcile_hub_live_sessions() -> None:
    active_staff: set[int] = set()
    for row in list_active_service_staff():
        uid = int(row.get("staff_id") or 0)
        if uid:
            active_staff.add(uid)
    if not HUB_URL or not HUB_SECRET:
        return
    try:
        req = urllib.request.Request(
            f"{HUB_URL.rstrip('/')}/api/live",
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for sess in data.get("sessions") or []:
            if str(sess.get("bot_key") or "") != "ombor":
                continue
            uid = int(sess.get("tg_id") or 0)
            if uid and uid not in active_staff:
                push_session_end_background(tg_id=uid, bot_key="ombor", activity_type="ombor")
                log.info("Hub live reconcile: ombor sessiya yopildi tg=%s", uid)
    except Exception as e:
        log.debug("hub live reconcile: %s", e)
