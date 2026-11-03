import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.schemas import (
    DeletePayload,
    NotePayload,
    ParsedIntent,
    ReminderPayload,
    SearchPayload,
)


def _tz(name: str) -> ZoneInfo | timezone:
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone.utc


def _title_from_text(text: str, max_len: int = 24) -> str:
    cleaned = re.sub(r"^(记一下|记录|备忘|提醒我|帮我|请|删除|删掉|清除|找一下|查找|搜一下)[:：，,\s]*", "", text).strip()
    return cleaned[:max_len] or text[:max_len]


def parse_with_rules(text: str, *, now: datetime | None = None, timezone_name: str = "Asia/Shanghai") -> ParsedIntent:
    now = now or datetime.now(_tz(timezone_name))
    if now.tzinfo is None:
        now = now.replace(tzinfo=_tz(timezone_name))

    compact = text.strip()
    item_type = "any"
    if "提醒" in compact:
        item_type = "reminder"
    elif "记事" in compact or "记录" in compact or "笔记" in compact:
        item_type = "note"

    if re.search(r"删除|删掉|清除", compact):
        query = re.sub(r"删除|删掉|清除|一下|这个|这条|记录|提醒|记事", " ", compact).strip() or compact
        return ParsedIntent(
            intent="delete",
            confidence=0.78,
            needs_confirmation=True,
            delete=DeletePayload(query=query, item_type=item_type, require_confirmation=True),
        )

    if re.search(r"查找|找一下|搜一下|搜索|有没有|之前", compact):
        query = re.sub(r"查找|找一下|搜一下|搜索|有没有|之前|关于|记录|提醒|记事", " ", compact).strip() or compact
        return ParsedIntent(
            intent="search",
            confidence=0.8,
            search=SearchPayload(query=query, item_type=item_type, limit=20),
        )

    interval_match = re.search(r"每隔\s*(\d+)\s*(分钟|分|小时|个小时)", compact)
    if interval_match:
        amount = int(interval_match.group(1))
        unit = interval_match.group(2)
        seconds = amount * 60 if unit in {"分钟", "分"} else amount * 3600
        return ParsedIntent(
            intent="reminder",
            confidence=0.86,
            reminder=ReminderPayload(
                title=_title_from_text(compact),
                content=compact,
                due_at=None,
                recurrence_type="interval",
                interval_seconds=seconds,
                timezone=timezone_name,
            ),
        )

    relative_match = re.search(r"(\d+)\s*(分钟|分|小时|个小时)后", compact)
    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2)
        delta = timedelta(minutes=amount) if unit in {"分钟", "分"} else timedelta(hours=amount)
        due_at = now + delta
        return ParsedIntent(
            intent="reminder",
            confidence=0.84,
            reminder=ReminderPayload(
                title=_title_from_text(compact),
                content=compact,
                due_at=due_at.isoformat(),
                recurrence_type="none",
                timezone=timezone_name,
            ),
        )

    if "提醒" in compact or "叫我" in compact or "到点" in compact:
        return ParsedIntent(
            intent="reminder",
            confidence=0.62,
            needs_confirmation=True,
            clarification_question="你想让我什么时候提醒？",
            reminder=ReminderPayload(
                title=_title_from_text(compact),
                content=compact,
                recurrence_type="none",
                timezone=timezone_name,
            ),
        )

    if re.search(r"记一下|记录|备忘|笔记", compact) or len(compact) >= 8:
        content = re.sub(r"^(记一下|记录|备忘)[:：，,\s]*", "", compact).strip() or compact
        return ParsedIntent(
            intent="note",
            confidence=0.72,
            note=NotePayload(title=_title_from_text(content), content=content),
        )

    return ParsedIntent(
        intent="unknown",
        confidence=0.2,
        needs_confirmation=True,
        clarification_question="我不确定你想记录、提醒、查找还是删除，可以换个说法吗？",
    )
