from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

IntentType = Literal["reminder", "note", "search", "delete", "unknown"]
ItemType = Literal["any", "note", "reminder"]
RecurrenceType = Literal["none", "interval", "daily", "weekly", "monthly", "custom"]


class NotePayload(BaseModel):
    title: str | None = None
    content: str


class ReminderPayload(BaseModel):
    title: str
    content: str
    due_at: str | None = None
    recurrence_type: RecurrenceType = "none"
    interval_seconds: int | None = None
    timezone: str = "Asia/Shanghai"


class SearchPayload(BaseModel):
    query: str
    item_type: ItemType = "any"
    time_hint: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class DeletePayload(BaseModel):
    query: str
    item_type: ItemType = "any"
    require_confirmation: bool = True


class ParsedIntent(BaseModel):
    intent: IntentType
    confidence: float = Field(ge=0, le=1)
    needs_confirmation: bool = False
    clarification_question: str | None = None
    note: NotePayload | None = None
    reminder: ReminderPayload | None = None
    search: SearchPayload | None = None
    delete: DeletePayload | None = None


class CommandRequest(BaseModel):
    text: str = Field(min_length=1)
    timezone: str = "Asia/Shanghai"
    client_now: datetime | None = None
    auto_execute: bool = True


class ItemCreate(BaseModel):
    item_type: Literal["note", "reminder"]
    title: str | None = None
    content: str
    raw_text: str | None = None
    due_at: datetime | None = None
    timezone: str | None = None
    recurrence_type: str | None = "none"
    interval_seconds: int | None = None
    next_run_at: datetime | None = None


class ItemUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    status: str | None = None
    due_at: datetime | None = None
    recurrence_type: str | None = None
    interval_seconds: int | None = None
    next_run_at: datetime | None = None


class ItemRead(BaseModel):
    id: int
    item_type: str
    title: str | None
    content: str
    raw_text: str
    status: str
    created_at: datetime
    updated_at: datetime
    due_at: datetime | None
    timezone: str | None
    recurrence_type: str | None
    interval_seconds: int | None
    next_run_at: datetime | None
    last_triggered_at: datetime | None


class ReminderEventRead(BaseModel):
    id: int
    item_id: int
    triggered_at: datetime
    message: str
    delivered: bool
    acknowledged_at: datetime | None


class CommandResponse(BaseModel):
    parsed: ParsedIntent
    result: dict
