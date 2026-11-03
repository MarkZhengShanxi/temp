import asyncio
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, SQLModel, create_engine

from app.models import Item, ReminderEvent
from app.services import scheduler as scheduler_module


def test_due_reminder_creates_event_and_marks_done(monkeypatch) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(scheduler_module, "engine", engine)
    now = datetime(2026, 11, 3, 2, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        session.add(Item(item_type="reminder", title="开会", content="开会", raw_text="开会", next_run_at=now))
        session.commit()

    events = asyncio.run(scheduler_module.check_due_reminders(now=now))

    assert len(events) == 1
    with Session(engine) as session:
        item = session.get(Item, 1)
        assert item is not None
        assert item.status == "done"
        assert session.get(ReminderEvent, 1) is not None


def test_interval_reminder_advances_next_run(monkeypatch) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(scheduler_module, "engine", engine)
    now = datetime(2026, 11, 3, 2, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        session.add(
            Item(
                item_type="reminder",
                title="喝水",
                content="喝水",
                raw_text="喝水",
                recurrence_type="interval",
                interval_seconds=300,
                next_run_at=now,
            )
        )
        session.commit()

    asyncio.run(scheduler_module.check_due_reminders(now=now))

    with Session(engine) as session:
        item = session.get(Item, 1)
        assert item is not None
        assert item.status == "active"
        assert item.next_run_at == now + timedelta(seconds=300)


def test_done_reminder_does_not_fire(monkeypatch) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(scheduler_module, "engine", engine)
    now = datetime(2026, 11, 3, 2, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        session.add(Item(item_type="reminder", title="完成", content="完成", raw_text="完成", status="done", next_run_at=now))
        session.commit()

    events = asyncio.run(scheduler_module.check_due_reminders(now=now))

    assert events == []
