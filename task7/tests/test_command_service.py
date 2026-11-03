from datetime import datetime, timedelta, timezone

from sqlmodel import Session, SQLModel, create_engine

from app.models import Item
from app.schemas import CommandRequest, DeletePayload, NotePayload, ParsedIntent, ReminderPayload, SearchPayload
from app.services.command_service import CommandService


class FakeParser:
    def __init__(self, parsed: ParsedIntent) -> None:
        self.parsed = parsed

    def parse(self, text: str, *, timezone_name: str, client_now: datetime | None = None) -> ParsedIntent:
        return self.parsed


def make_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_create_note() -> None:
    session = make_session()
    parsed = ParsedIntent(intent="note", confidence=0.9, note=NotePayload(title="客户预算", content="客户预算下周确认"))
    service = CommandService(parser=FakeParser(parsed))

    _, result = service.handle(session, CommandRequest(text="记一下：客户预算下周确认"))

    assert result["action"] == "created"
    assert result["item"]["item_type"] == "note"


def test_create_interval_reminder() -> None:
    session = make_session()
    parsed = ParsedIntent(
        intent="reminder",
        confidence=0.9,
        reminder=ReminderPayload(title="喝水", content="喝水", recurrence_type="interval", interval_seconds=300),
    )
    service = CommandService(parser=FakeParser(parsed))
    now = datetime(2026, 11, 3, 2, 0, tzinfo=timezone.utc)

    _, result = service.handle(session, CommandRequest(text="每隔5分钟提醒我喝水", client_now=now))

    assert result["action"] == "created"
    assert result["item"]["recurrence_type"] == "interval"
    assert result["item"]["interval_seconds"] == 300


def test_search_existing_items() -> None:
    session = make_session()
    session.add(Item(item_type="note", title="合同", content="合同周五签", raw_text="合同周五签"))
    session.commit()
    parsed = ParsedIntent(intent="search", confidence=0.9, search=SearchPayload(query="合同"))
    service = CommandService(parser=FakeParser(parsed))

    _, result = service.handle(session, CommandRequest(text="找一下合同"))

    assert result["action"] == "searched"
    assert result["count"] == 1


def test_delete_returns_candidates_by_default() -> None:
    session = make_session()
    session.add(Item(item_type="reminder", title="喝水", content="喝水", raw_text="喝水"))
    session.commit()
    parsed = ParsedIntent(intent="delete", confidence=0.9, delete=DeletePayload(query="喝水", item_type="reminder"))
    service = CommandService(parser=FakeParser(parsed))

    _, result = service.handle(session, CommandRequest(text="删除喝水提醒"))

    assert result["action"] == "delete_candidates"
    assert result["count"] == 1


def test_high_confidence_delete_can_physically_delete() -> None:
    session = make_session()
    session.add(Item(item_type="note", title="合同", content="合同", raw_text="合同"))
    session.commit()
    parsed = ParsedIntent(
        intent="delete",
        confidence=0.95,
        delete=DeletePayload(query="合同", item_type="note", require_confirmation=False),
    )
    service = CommandService(parser=FakeParser(parsed))

    _, result = service.handle(session, CommandRequest(text="删除合同记录"))

    assert result["action"] == "deleted"
    assert session.get(Item, result["item"]["id"]) is None
