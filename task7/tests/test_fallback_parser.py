from datetime import datetime
from zoneinfo import ZoneInfo

from app.ai.fallback_parser import parse_with_rules


def test_parse_interval_reminder() -> None:
    parsed = parse_with_rules("每隔5分钟提醒我喝水", now=datetime(2026, 11, 3, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert parsed.intent == "reminder"
    assert parsed.reminder is not None
    assert parsed.reminder.recurrence_type == "interval"
    assert parsed.reminder.interval_seconds == 300


def test_parse_relative_reminder() -> None:
    parsed = parse_with_rules("10分钟后提醒我开会", now=datetime(2026, 11, 3, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert parsed.intent == "reminder"
    assert parsed.reminder is not None
    assert parsed.reminder.due_at is not None
    assert "10:10" in parsed.reminder.due_at


def test_parse_note() -> None:
    parsed = parse_with_rules("记一下：客户预算下周确认")

    assert parsed.intent == "note"
    assert parsed.note is not None
    assert "客户预算" in parsed.note.content


def test_parse_search() -> None:
    parsed = parse_with_rules("找一下合同相关的记录")

    assert parsed.intent == "search"
    assert parsed.search is not None
    assert "合同" in parsed.search.query


def test_parse_delete() -> None:
    parsed = parse_with_rules("删除喝水提醒")

    assert parsed.intent == "delete"
    assert parsed.delete is not None
    assert "喝水" in parsed.delete.query
