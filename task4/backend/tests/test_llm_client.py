import pytest

from app.llm_client import extract_json_object, LLMClientError, OpenAICompatibleClient
from app.config import Settings
from app.schemas import LLMConfig


def test_extract_json_object_plain():
    assert extract_json_object('{"type":"done","summary":"ok"}') == {
        "type": "done",
        "summary": "ok",
    }


def test_extract_json_object_fenced():
    assert extract_json_object('```json\n{"type":"scroll","amount":500}\n```') == {
        "type": "scroll",
        "amount": 500,
    }


def test_extract_json_object_invalid():
    with pytest.raises(LLMClientError):
        extract_json_object("not json")


def test_resolve_config_trims_base_url():
    client = OpenAICompatibleClient(
        Settings(openai_base_url="https://api.example.com/v1/", openai_api_key="env-key")
    )
    resolved = client.resolve_config(
        LLMConfig(base_url="http://localhost:11434/v1/", model="local", api_key="abc")
    )
    assert resolved.base_url == "http://localhost:11434/v1"
    assert resolved.chat_completions_url == "http://localhost:11434/v1/chat/completions"
    assert resolved.api_key == "abc"
    assert resolved.model == "local"
