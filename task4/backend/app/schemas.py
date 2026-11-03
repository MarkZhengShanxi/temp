from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, SecretStr, field_validator


ActionType = Literal[
    "click",
    "type",
    "clear",
    "press_key",
    "select",
    "scroll",
    "wait",
    "read_page",
    "open_tab",
    "switch_tab",
    "close_tab",
    "ask_user",
    "done",
    "fail",
]

RunStatus = Literal[
    "idle",
    "thinking",
    "awaiting_confirmation",
    "executing",
    "completed",
    "failed",
    "stopped",
]


class LLMConfig(BaseModel):
    base_url: str | None = None
    api_key: SecretStr | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=128000)

    @field_validator("base_url")
    @classmethod
    def strip_base_url(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class BrowserElement(BaseModel):
    id: str
    tag: str
    role: str | None = None
    type: str | None = None
    text: str | None = None
    aria_label: str | None = None
    placeholder: str | None = None
    selector: str | None = None
    href: str | None = None
    value: str | None = None
    visible: bool = True
    enabled: bool = True
    rect: dict[str, Any] = Field(default_factory=dict)


class BrowserState(BaseModel):
    url: str = ""
    title: str | None = None
    text: str | None = None
    viewport: dict[str, Any] = Field(default_factory=dict)
    elements: list[BrowserElement] = Field(default_factory=list)
    browser: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ActionResult(BaseModel):
    ok: bool
    message: str | None = None
    error: str | None = None
    observation: BrowserState | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class AgentAction(BaseModel):
    type: ActionType
    rationale: str = ""
    target_element_id: str | None = None
    text: str | None = None
    key: str | None = None
    direction: Literal["up", "down", "left", "right"] | None = None
    amount: int | None = Field(default=None, ge=0)
    tab_index: int | None = Field(default=None, ge=0)
    url: str | None = None
    requires_confirmation: bool = False
    summary: str | None = None


class AgentOptions(BaseModel):
    max_steps: int | None = Field(default=None, ge=1, le=100)
    require_confirmation_for_submit: bool = True


class AgentStartRequest(BaseModel):
    task: str
    browser_state: BrowserState
    llm_config: LLMConfig | None = None
    options: AgentOptions = Field(default_factory=AgentOptions)


class AgentStepRequest(BaseModel):
    run_id: str
    browser_state: BrowserState
    last_action_result: ActionResult | None = None
    user_confirmation: Literal["allow", "deny"] | None = None


class AgentStopRequest(BaseModel):
    run_id: str


class AgentStepRecord(BaseModel):
    index: int
    browser_state: BrowserState
    action: AgentAction | None = None
    result: ActionResult | None = None
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    task: str
    status: RunStatus = "idle"
    llm_config: LLMConfig | None = None
    options: AgentOptions = Field(default_factory=AgentOptions)
    steps: list[AgentStepRecord] = Field(default_factory=list)
    pending_action: AgentAction | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentStepResponse(BaseModel):
    run_id: str
    status: RunStatus
    step_index: int
    message: str
    action: AgentAction | None = None
    requires_confirmation: bool = False
    summary: str | None = None


class ConfigTestRequest(BaseModel):
    llm_config: LLMConfig


class ConfigTestResponse(BaseModel):
    ok: bool
    model: str | None = None
    message: str
