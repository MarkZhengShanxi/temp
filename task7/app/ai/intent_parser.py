import json
from datetime import datetime

import anthropic

from app.ai.anthropic_client import create_anthropic_client
from app.ai.fallback_parser import parse_with_rules
from app.ai.prompts import INTENT_SYSTEM_PROMPT
from app.config import get_settings
from app.schemas import ParsedIntent


class IntentParser:
    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self.settings = get_settings()
        self.client = client or create_anthropic_client()

    def parse(self, text: str, *, timezone_name: str, client_now: datetime | None = None) -> ParsedIntent:
        now = client_now or datetime.now().astimezone()
        user_prompt = (
            f"当前时间：{now.isoformat()}\n"
            f"用户时区：{timezone_name}\n"
            f"用户输入：{text}"
        )
        try:
            return self._parse_with_claude(user_prompt)
        except (
            anthropic.APIConnectionError,
            anthropic.APIStatusError,
            anthropic.APITimeoutError,
            ValueError,
            json.JSONDecodeError,
        ):
            return parse_with_rules(text, now=now, timezone_name=timezone_name)

    def _parse_with_claude(self, user_prompt: str) -> ParsedIntent:
        model = self.settings.resolved_anthropic_model
        if self.settings.use_claude_params and hasattr(self.client.messages, "parse"):
            response = self.client.messages.parse(
                model=model,
                max_tokens=self.settings.anthropic_max_tokens,
                thinking={"type": "adaptive"},
                output_config={"effort": self.settings.anthropic_effort},
                system=INTENT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                output_format=ParsedIntent,
            )
            parsed = getattr(response, "parsed_output", None)
            if isinstance(parsed, ParsedIntent):
                return parsed
            if parsed is not None:
                return ParsedIntent.model_validate(parsed)

        schema = ParsedIntent.model_json_schema()
        if self.settings.use_claude_params:
            response = self.client.messages.create(
                model=model,
                max_tokens=self.settings.anthropic_max_tokens,
                thinking={"type": "adaptive"},
                output_config={
                    "effort": self.settings.anthropic_effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
                system=INTENT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
        else:
            response = self.client.messages.create(
                model=model,
                max_tokens=self.settings.anthropic_max_tokens,
                system=INTENT_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"{user_prompt}\n\n"
                            "请只返回 JSON，不要 Markdown 代码块。JSON 必须符合这个 schema：\n"
                            f"{json.dumps(schema, ensure_ascii=False)}"
                        ),
                    }
                ],
            )
        if response.stop_reason == "refusal":
            raise ValueError("Claude refused to parse this request")
        text = next((block.text for block in response.content if block.type == "text"), "")
        return ParsedIntent.model_validate_json(text)
