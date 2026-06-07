"""Paste parser uchun vaqt parse (yordamchi forward_import dan nusxa)."""

from __future__ import annotations

import re


def parse_uz_duration(text: str) -> int:
    sl = (text or "").lower()
    total = 0
    h = re.search(r"(\d+)\s*soat", sl)
    m = re.search(r"(\d+)\s*daqiqa", sl)
    s = re.search(r"(\d+)\s*soniya", sl)
    if h:
        total += int(h.group(1)) * 3600
    if m:
        total += int(m.group(1)) * 60
    if s:
        total += int(s.group(1))
    if total:
        return total
    mm = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", sl.strip())
    if mm:
        if mm.group(3) is not None:
            return int(mm.group(1)) * 3600 + int(mm.group(2)) * 60 + int(mm.group(3))
        return int(mm.group(1)) * 60 + int(mm.group(2))
    dm = re.search(r"(\d+)\s*daq", sl)
    if dm:
        total += int(dm.group(1)) * 60
    sm = re.search(r"(\d+)\s*son", sl)
    if sm:
        total += int(sm.group(1))
    return total
