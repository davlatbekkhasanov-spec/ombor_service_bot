"""Guruh/paste matnidan orders_seed.py generatsiya qilish."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from employee_registry import resolve_employee_tg_id  # noqa: E402
from forward_import_local import parse_uz_duration  # noqa: E402

MSG_SPLIT = re.compile(
    r"(?=\[\d{2}\.\d{2}\.\d{4}\s+\d{1,2}:\d{2}\]|"
    r"(?:🙋|👀|📦|ℹ️)\s+(?:Xizmat|Mijoz|Tovar|Savol))",
    re.M,
)

KIND_MAP = {
    "xizmat so'rovi": ("call_staff", "🙋 Xizmat so'rovi"),
    "mijozga qarang": ("check_client", "👀 Mijozga qarang"),
    "tovar buyurtma": ("product_order", "📦 Tovar buyurtma"),
    "savol": ("info", "ℹ️ Savol"),
}


def _kind_from_block(block: str) -> tuple[str, str]:
    bl = block.lower()
    for key, val in KIND_MAP.items():
        if key in bl:
            return val
    if "buyurtma:" in bl:
        return KIND_MAP["tovar buyurtma"]
    if "xizmat:" in bl:
        return KIND_MAP["xizmat so'rovi"]
    return ("product_order", "📦 Tovar buyurtma")


def _staff_names(block: str) -> list[str]:
    names: list[str] = []
    for pat in (
        r"Jamoa[^:]*:\s*(.+?)(?:\n|⏱|👤|📦|$)",
        r"Xizmat ko.?rsat\w*\s*:\s*(.+?)(?:\n|🔗|⏱|✅|$)",
    ):
        m = re.search(pat, block, re.I | re.S)
        if not m:
            continue
        raw = m.group(1).strip()
        for part in re.split(r",| va |/|;", raw):
            part = part.strip()
            if part and part not in names:
                names.append(part)
    return names


def parse_order_block(block: str) -> dict | None:
    if "tugadi:" not in block.lower() and "bajarildi" not in block.lower():
        return None
    if not re.search(r"#\s*\d+", block):
        return None

    done_m = re.search(r"Tugadi:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)", block, re.I)
    if not done_m:
        return None
    finished_at = done_m.group(1)
    if len(finished_at) == 16:
        finished_at += ":00"

    oid_m = re.search(r"#\s*(\d+)", block)
    order_id = int(oid_m.group(1)) if oid_m else None

    created_m = re.search(r"Keldi:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)", block, re.I)
    created_at = created_m.group(1) if created_m else finished_at[:10] + " 00:00:00"
    if len(created_at) == 16:
        created_at += ":00"

    assigned_m = re.search(r"Band qilindi:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)", block, re.I)
    assigned_at = assigned_m.group(1) if assigned_m else created_at
    if len(assigned_at) == 16:
        assigned_at += ":00"

    dur_m = re.search(r"Xizmat vaqti:\s*(.+?)(?:\n|✅|$)", block, re.I | re.S)
    service_seconds = parse_uz_duration(dur_m.group(1)) if dur_m else 0
    if not service_seconds:
        service_seconds = parse_uz_duration(block)
    service_minutes = max(1, (service_seconds + 59) // 60) if service_seconds else 0

    user_m = re.search(r"Mijoz:\s*(.+?)(?:\n|📱|$)", block, re.I)
    full_name = user_m.group(1).strip() if user_m else "—"
    uid_m = re.search(r"ID\s+(\d+)", block)
    user_id = int(uid_m.group(1)) if uid_m else 0
    un_m = re.search(r"📱\s*@(\w+)", block)
    username = un_m.group(1) if un_m else None

    request_type, kind_label = _kind_from_block(block)
    text_m = re.search(r"(?:Buyurtma|Xizmat):\s*\n(.+?)(?:\n\[|\Z)", block, re.I | re.S)
    text = text_m.group(1).strip() if text_m else kind_label.split(maxsplit=1)[-1]

    staff_raw = _staff_names(block)
    staff: list[dict] = []
    for i, name in enumerate(staff_raw):
        sid = resolve_employee_tg_id(name)
        if not sid:
            continue
        staff.append({"staff_id": sid, "staff_name": name, "is_lead": i == 0})
    if not staff:
        return None

    lead = staff[0]
    return {
        "id": order_id,
        "user_id": user_id,
        "username": username,
        "full_name": full_name,
        "request_type": request_type,
        "kind_label": kind_label,
        "text": text[:500],
        "status": "bajarildi",
        "created_at": created_at,
        "updated_at": finished_at,
        "assigned_to": lead["staff_name"],
        "assigned_to_id": lead["staff_id"],
        "assigned_at": assigned_at,
        "finished_at": finished_at,
        "service_seconds": service_seconds,
        "service_minutes": service_minutes,
        "staff": staff,
        "seed_key": f"{finished_at}|{lead['staff_id']}|{kind_label}",
    }


def parse_text(body: str) -> list[dict]:
    chunks = MSG_SPLIT.split(body)
    out: list[dict] = []
    seen: set[str] = set()
    for chunk in chunks:
        row = parse_order_block(chunk)
        if not row:
            continue
        key = row.pop("seed_key")
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    out.sort(key=lambda r: (r["finished_at"], r.get("id") or 0))
    return out


def render_py(rows: list[dict], version: int, note: str) -> str:
    lines = [
        '"""Ombor arizalari — deploydan keyin avtomatik tiklanadi."""',
        "",
        "from __future__ import annotations",
        "",
        f"ORDERS_SEED_VERSION = {version}",
        f'ORDERS_SEED_NOTE = "{note}"',
        "",
        "ORDERS_SEED_ROWS: tuple[dict, ...] = (",
    ]
    for row in rows:
        lines.append("    {")
        for k, v in row.items():
            if k == "staff":
                lines.append(f'        "staff": {v!r},')
            elif isinstance(v, str):
                lines.append(f'        "{k}": {v!r},')
            elif v is None:
                lines.append(f'        "{k}": None,')
            else:
                lines.append(f'        "{k}": {v},')
        lines.append("    },")
    lines.append(")")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    sources = [
        ROOT.parent / "davlat-yordamchi-bot" / "tools" / "paste_input.txt",
        ROOT.parent / "davlat-yordamchi-bot" / "tools" / "paste_2026-06-04.txt",
    ]
    body = ""
    for path in sources:
        if path.is_file():
            body += path.read_text(encoding="utf-8") + "\n\n"
    rows = parse_text(body)
    out = ROOT / "orders_seed.py"
    note = "02–04.06.2026 guruh kartalari (paste); deployda SQLite tiklanadi"
    out.write_text(render_py(rows, version=1, note=note), encoding="utf-8")
    print(f"Wrote {len(rows)} orders -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
