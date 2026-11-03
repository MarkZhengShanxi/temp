from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.routes_commands import get_command_service
from app.database import get_session
from app.main import app
from app.schemas import NotePayload, ParsedIntent, ReminderPayload
from app.services.command_service import CommandService


class FakeParser:
    def parse(self, text: str, **kwargs) -> ParsedIntent:
        if "每隔5分钟" in text:
            return ParsedIntent(
                intent="reminder",
                confidence=0.9,
                reminder=ReminderPayload(title="喝水", content="喝水", recurrence_type="interval", interval_seconds=300),
            )
        return ParsedIntent(
            intent="note",
            confidence=0.9,
            note=NotePayload(title="客户预算", content="客户预算下周确认"),
        )


def make_test_client() -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def override_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_command_service] = lambda: CommandService(parser=FakeParser())
    return TestClient(app)


def test_command_endpoint_creates_note_with_fallback() -> None:
    with make_test_client() as client:
        response = client.post(
            "/api/commands",
            json={"text": "记一下：客户预算下周确认", "timezone": "Asia/Shanghai"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["parsed"]["intent"] == "note"
        assert data["result"]["action"] == "created"

        items = client.get("/api/items").json()
        assert len(items) == 1
        assert "客户预算" in items[0]["content"]


def test_command_endpoint_creates_interval_reminder_with_fallback() -> None:
    with make_test_client() as client:
        response = client.post(
            "/api/commands",
            json={"text": "每隔5分钟提醒我喝水", "timezone": "Asia/Shanghai"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["parsed"]["intent"] == "reminder"
        assert data["result"]["item"]["interval_seconds"] == 300


def test_search_and_physical_delete() -> None:
    with make_test_client() as client:
        created = client.post(
            "/api/items",
            json={"item_type": "note", "title": "合同", "content": "合同周五签"},
        ).json()

        results = client.get("/api/search", params={"q": "合同"}).json()
        assert len(results) == 1

        delete_response = client.delete(f"/api/items/{created['id']}")
        assert delete_response.status_code == 200

        missing = client.get(f"/api/items/{created['id']}")
        assert missing.status_code == 404
