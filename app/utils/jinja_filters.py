from __future__ import annotations

from datetime import datetime, date
from typing import Any


_RU_MONTHS_GEN = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def ru_date(value: Any) -> str:
    """Format date/datetime/ISO string to '15 августа 2025'. Fallback to str(value)."""
    dt: datetime | None = None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    elif isinstance(value, str):
        try:
            # Try to parse ISO-like strings
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            dt = None
    if not dt:
        return str(value)
    month = _RU_MONTHS_GEN.get(dt.month, "")
    return f"{dt.day} {month} {dt.year}"


