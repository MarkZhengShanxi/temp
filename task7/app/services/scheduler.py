from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import Session, col, select

from app.database import engine
from app.models import Item, ReminderEvent
from app.services.event_bus import reminder_event_bus
from app.services.reminder_service import advance_after_trigger


class ReminderScheduler:
    def __init__(self, poll_seconds: int) -> None:
        self.scheduler = AsyncIOScheduler(timezone=timezone.utc)
        self.poll_seconds = poll_seconds

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.add_job(self.check_due_reminders, "interval", seconds=self.poll_seconds, id="check_due_reminders")
            self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def check_due_reminders(self) -> None:
        await check_due_reminders()


async def check_due_reminders(now: datetime | None = None) -> list[ReminderEvent]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    events: list[ReminderEvent] = []

    with Session(engine) as session:
        statement = (
            select(Item)
            .where(Item.item_type == "reminder")
            .where(Item.status == "active")
            .where(Item.next_run_at.is_not(None))
            .where(col(Item.next_run_at) <= now)
        )
        items = list(session.exec(statement).all())
        for item in items:
            event = ReminderEvent(
                item_id=item.id or 0,
                triggered_at=now,
                message=item.title or item.content,
                delivered=False,
            )
            session.add(event)
            advance_after_trigger(item, now=now)
            events.append(event)
        session.commit()
        for event in events:
            session.refresh(event)

    for event in events:
        await reminder_event_bus.publish(
            {
                "type": "reminder_due",
                "event_id": event.id,
                "item_id": event.item_id,
                "message": event.message,
                "triggered_at": event.triggered_at.isoformat(),
            }
        )
    return events
