from datetime import datetime, timezone

from sqlmodel import Session

from app.models import Item
from app.schemas import NotePayload


def create_note(session: Session, payload: NotePayload, *, raw_text: str) -> Item:
    item = Item(
        item_type="note",
        title=payload.title,
        content=payload.content,
        raw_text=raw_text,
        status="active",
        updated_at=datetime.now(timezone.utc),
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item
