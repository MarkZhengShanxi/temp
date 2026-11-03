from sqlmodel import Session, col, or_, select

from app.models import Item


def search_items(
    session: Session,
    *,
    query: str | None = None,
    item_type: str = "any",
    status: str | None = "active",
    limit: int = 50,
) -> list[Item]:
    statement = select(Item)
    if status:
        statement = statement.where(Item.status == status)
    if item_type != "any":
        statement = statement.where(Item.item_type == item_type)
    if query:
        pattern = f"%{query.strip()}%"
        statement = statement.where(
            or_(
                col(Item.title).like(pattern),
                col(Item.content).like(pattern),
                col(Item.raw_text).like(pattern),
            )
        )
    statement = statement.order_by(col(Item.created_at).desc()).limit(limit)
    return list(session.exec(statement).all())
