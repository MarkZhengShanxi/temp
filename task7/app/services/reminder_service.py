from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlmodel import Session

from app.models import Item
from app.schemas import ReminderPayload


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _next_daily(due_at: datetime | None, now: datetime) -> datetime | None:
    if due_at is None:
        return None
    candidate = due_at.astimezone(timezone.utc)
    while candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def create_reminder(session: Session, payload: ReminderPayload, *, raw_text: str, now: datetime | None = None) -> Item:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    due_at = _parse_datetime(payload.due_at)
    recurrence_type = payload.recurrence_type or "none"
    next_run_at = due_at

    if recurrence_type == "interval" and payload.interval_seconds:
        next_run_at = due_at or (now + timedelta(seconds=payload.interval_seconds))
    elif recurrence_type == "daily":
        next_run_at = _next_daily(due_at, now)

    item = Item(
        item_type="reminder",
        title=payload.title,
        content=payload.content,
        raw_text=raw_text,
        status="active",
        due_at=due_at,
        timezone=payload.timezone,
        recurrence_type=recurrence_type,
        interval_seconds=payload.interval_seconds,
        next_run_at=next_run_at,
        updated_at=datetime.now(timezone.utc),
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def advance_after_trigger(item: Item, *, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    item.last_triggered_at = now
    item.updated_at = now
    if item.recurrence_type == "interval" and item.interval_seconds:
        item.next_run_at = now + timedelta(seconds=item.interval_seconds)
    elif item.recurrence_type == "daily" and item.next_run_at:
        item.next_run_at = item.next_run_at + timedelta(days=1)
        while item.next_run_at <= now:
            item.next_run_at += timedelta(days=1)
    else:
        item.status = "done"
        item.next_run_at = None
