from sqlmodel import Session

from app.models import Item
from app.services.search_service import search_items


def find_delete_candidates(session: Session, *, query: str, item_type: str = "any") -> list[Item]:
    return search_items(session, query=query, item_type=item_type, status="active", limit=20)


def delete_item(session: Session, item: Item) -> None:
    session.delete(item)
    session.commit()
