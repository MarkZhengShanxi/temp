from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Item(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    item_type: str = Field(index=True)  # note | reminder
    title: str | None = Field(default=None, index=True)
    content: str
    raw_text: str
    status: str = Field(default="active", index=True)  # active | done
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)

    due_at: datetime | None = Field(default=None, index=True)
    timezone: str | None = None
    recurrence_type: str | None = Field(default="none", index=True)
    interval_seconds: int | None = None
    next_run_at: datetime | None = Field(default=None, index=True)
    last_triggered_at: datetime | None = None


class ReminderEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="item.id", index=True)
    triggered_at: datetime = Field(default_factory=utc_now, index=True)
    message: str
    delivered: bool = Field(default=False, index=True)
    acknowledged_at: datetime | None = None
