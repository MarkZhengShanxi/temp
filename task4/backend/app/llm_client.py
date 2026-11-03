from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import SecretStr

from app.config import Settings
from app.schemas import LLMConfig


logger = logging.getLogger("browser_agent.llm")


class LLMClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResolvedLLMConfig:
    base_url: str
    api_key: str | None
    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: float

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


class OpenAICompatibleClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def resolve_config(self, override: LLMConfig | None = None) -> ResolvedLLMConfig:
        override = override or LLMConfig()
        api_key: SecretStr | None = override.api_key
        return ResolvedLLMConfig(
            base_url=(override.base_url or self.settings.openai_base_url).rstrip("/"),
            api_key=(api_key.get_secret_value() if api_key else self.settings.openai_api_key),
            model=override.model or self.settings.openai_model,
            temperature=(
                override.temperature
                if override.temperature is not None
                else self.settings.openai_temperature
            ),
            max_tokens=(
                override.max_tokens
                if override.max_tokens is not None
                else self.settings.openai_max_tokens
            ),
            timeout_seconds=self.settings.openai_timeout_seconds,
        )

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig | None = None,
    ) -> dict[str, Any]:
        content = await self.chat_text(messages, config=config, json_mode=True)
        return extract_json_object(content)

    async def chat_text(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig | None = None,
        json_mode: bool = False,
    ) -> str:
        resolved = self.resolve_config(config)
        if not resolved.api_key:
            raise LLMClientError("Missing API key. Provide one in the Side Panel or backend .env.")

        payload: dict[str, Any] = {
            "model": resolved.model,
            "messages": messages,
            "temperature": resolved.temperature,
            "max_tokens": resolved.max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {resolved.api_key}",
        }

        logger.info(
            "chat completions request url=%s model=%s json_mode=%s messages=%s",
            resolved.chat_completions_url,
            resolved.model,
            json_mode,
            len(messages),
        )
        async with httpx.AsyncClient(timeout=resolved.timeout_seconds) as client:
            try:
                response = await client.post(
                    resolved.chat_completions_url,
                    headers=headers,
                    json=payload,
                )
                logger.info("chat completions response status=%s", response.status_code)
                if response.status_code == 400 and "response_format" in payload:
                    logger.info("provider rejected initial request; retrying without response_format")
                    fallback_payload = dict(payload)
                    fallback_payload.pop("response_format", None)
                    response = await client.post(
                        resolved.chat_completions_url,
                        headers=headers,
                        json=fallback_payload,
                    )
                    logger.info("chat completions fallback response status=%s", response.status_code)
            except httpx.RequestError as exc:
                logger.warning("chat completions request failed: %s", exc)
                raise LLMClientError(f"LLM request failed: {exc}") from exc

        if response.status_code >= 400:
            detail = safe_response_text(response)
            raise LLMClientError(f"LLM provider returned {response.status_code}: {detail}")

        try:
            body = response.json()
        except json.JSONDecodeError as exc:
            raise LLMClientError("LLM provider returned non-JSON response.") from exc

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMClientError("LLM provider response did not contain choices[0].message.content.") from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMClientError("LLM provider returned empty content.")
        return content

    async def test_connection(self, config: LLMConfig) -> str:
        content = await self.chat_text(
            [
                {"role": "system", "content": "You are a connectivity test. Reply with exactly OK."},
                {"role": "user", "content": "Reply OK."},
            ],
            config=config,
            json_mode=False,
        )
        return content.strip()


def safe_response_text(response: httpx.Response) -> str:
    text = response.text.strip()
    if len(text) > 1000:
        return text[:1000] + "..."
    return text


def extract_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            value = json.loads(fenced.group(1))
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            value = json.loads(text[start : end + 1])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError as exc:
            raise LLMClientError(f"LLM returned invalid JSON: {exc}") from exc

    raise LLMClientError("LLM response did not contain a JSON object.")
