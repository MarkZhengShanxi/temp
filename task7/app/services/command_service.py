from datetime import datetime, timezone

from sqlmodel import Session

from app.ai.fallback_parser import parse_with_rules
from app.ai.intent_parser import IntentParser
from app.models import Item
from app.schemas import CommandRequest, ParsedIntent
from app.services.delete_service import delete_item, find_delete_candidates
from app.services.note_service import create_note
from app.services.reminder_service import create_reminder
from app.services.search_service import search_items

MIN_AUTO_CONFIDENCE = 0.65


def _item_to_dict(item: Item) -> dict:
    return item.model_dump(mode="json")


class CommandService:
    def __init__(self, parser: IntentParser | None = None) -> None:
        self.parser = parser or IntentParser()

    def handle(self, session: Session, request: CommandRequest) -> tuple[ParsedIntent, dict]:
        now = request.client_now or datetime.now(timezone.utc)
        parsed = self.parser.parse(request.text, timezone_name=request.timezone, client_now=now)
        if parsed.confidence < MIN_AUTO_CONFIDENCE and parsed.intent != "unknown":
            parsed = parse_with_rules(request.text, now=now, timezone_name=request.timezone)

        if parsed.intent == "note" and parsed.note:
            item = create_note(session, parsed.note, raw_text=request.text)
            return parsed, {"action": "created", "item": _item_to_dict(item)}

        if parsed.intent == "reminder" and parsed.reminder:
            if parsed.needs_confirmation and not parsed.reminder.due_at and parsed.reminder.recurrence_type != "interval":
                return parsed, {"action": "needs_confirmation", "message": parsed.clarification_question or "请补充提醒时间"}
            item = create_reminder(session, parsed.reminder, raw_text=request.text, now=now)
            return parsed, {"action": "created", "item": _item_to_dict(item)}

        if parsed.intent == "search" and parsed.search:
            items = search_items(
                session,
                query=parsed.search.query,
                item_type=parsed.search.item_type,
                status="active",
                limit=parsed.search.limit,
            )
            return parsed, {"action": "searched", "items": [_item_to_dict(item) for item in items], "count": len(items)}

        if parsed.intent == "delete" and parsed.delete:
            candidates = find_delete_candidates(
                session,
                query=parsed.delete.query,
                item_type=parsed.delete.item_type,
            )
            if not candidates:
                return parsed, {"action": "not_found", "items": [], "count": 0}
            if len(candidates) == 1 and parsed.confidence >= MIN_AUTO_CONFIDENCE and not parsed.delete.require_confirmation:
                deleted = candidates[0]
                deleted_dict = _item_to_dict(deleted)
                delete_item(session, deleted)
                return parsed, {"action": "deleted", "item": deleted_dict, "count": 1}
            return parsed, {
                "action": "delete_candidates",
                "items": [_item_to_dict(item) for item in candidates],
                "count": len(candidates),
                "message": "找到多条可能要删除的记录，请确认。" if len(candidates) > 1 else "请确认删除这条记录。",
            }

        return parsed, {"action": "unknown", "message": parsed.clarification_question or "我不确定该如何处理这段内容。"}
