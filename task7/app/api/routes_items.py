from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models import Item, ReminderEvent
from app.schemas import ItemCreate, ItemRead, ItemUpdate, ReminderEventRead
from app.services.delete_service import delete_item
from app.services.search_service import search_items

router = APIRouter(prefix="/api", tags=["items"])


@router.get("/items", response_model=list[ItemRead])
def list_items(
    type: str = Query(default="any"),
    q: str | None = Query(default=None),
    status: str | None = Query(default="active"),
    session: Session = Depends(get_session),
) -> list[Item]:
    return search_items(session, query=q, item_type=type, status=status, limit=100)


@router.post("/items", response_model=ItemRead)
def create_item(payload: ItemCreate, session: Session = Depends(get_session)) -> Item:
    now = datetime.now(timezone.utc)
    item = Item(
        item_type=payload.item_type,
        title=payload.title,
        content=payload.content,
        raw_text=payload.raw_text or payload.content,
        due_at=payload.due_at,
        timezone=payload.timezone,
        recurrence_type=payload.recurrence_type,
        interval_seconds=payload.interval_seconds,
        next_run_at=payload.next_run_at or payload.due_at,
        updated_at=now,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.get("/items/{item_id}", response_model=ItemRead)
def get_item(item_id: int, session: Session = Depends(get_session)) -> Item:
    item = session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.patch("/items/{item_id}", response_model=ItemRead)
def update_item(item_id: int, payload: ItemUpdate, session: Session = Depends(get_session)) -> Item:
    item = session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(item, key, value)
    item.updated_at = datetime.now(timezone.utc)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.delete("/items/{item_id}")
def remove_item(item_id: int, session: Session = Depends(get_session)) -> dict:
    item = session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    delete_item(session, item)
    return {"action": "deleted", "id": item_id}


@router.get("/search", response_model=list[ItemRead])
def search(q: str, type: str = "any", session: Session = Depends(get_session)) -> list[Item]:
    return search_items(session, query=q, item_type=type, status="active", limit=50)


@router.get("/reminder-events", response_model=list[ReminderEventRead])
def reminder_events(session: Session = Depends(get_session)) -> list[ReminderEvent]:
    return list(session.exec(select(ReminderEvent).order_by(ReminderEvent.triggered_at.desc())).all())


@router.post("/reminder-events/{event_id}/ack", response_model=ReminderEventRead)
def ack_reminder_event(event_id: int, session: Session = Depends(get_session)) -> ReminderEvent:
    event = session.get(ReminderEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Reminder event not found")
    event.delivered = True
    event.acknowledged_at = datetime.now(timezone.utc)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event
