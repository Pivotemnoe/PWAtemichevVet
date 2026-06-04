from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.security import utc_now


FOLLOWUP_DELAYS = {
    "red": timedelta(hours=6),
    "yellow": timedelta(hours=12),
}


def detect_followup_scenario(text: str | None) -> str:
    compact = " ".join(str(text or "").casefold().split())
    if any(marker in compact for marker in ("операц", "после операции", "шов", "кастрац", "стерилизац", "наркоз")):
        return "postop"
    if any(marker in compact for marker in ("рвота", "рвет", "рвёт", "понос", "диар", "жидкий стул", "отказ от корма", "не ест")):
        return "gi"
    if any(marker in compact for marker in ("хромает", "хромота", "ушиб", "падение", "упал", "не наступает", "лапу", "травм")):
        return "trauma"
    return "basic"


def followup_due_at(urgency_level: str | None) -> str | None:
    delay = FOLLOWUP_DELAYS.get((urgency_level or "").strip().lower())
    if not delay:
        return None
    return (utc_now() + delay).isoformat()


def followup_payload(*, complaint_text: str, summary: str | None, source: str = "pwa") -> dict[str, Any]:
    return {
        "source": source,
        "complaint": complaint_text,
        "summary": summary,
    }

