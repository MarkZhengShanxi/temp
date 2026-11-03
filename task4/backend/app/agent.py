from __future__ import annotations

from datetime import datetime, timezone

from pydantic import ValidationError

from app.config import Settings
from app.llm_client import LLMClientError, OpenAICompatibleClient
from app.planner import build_messages
from app.safety import apply_safety
from app.schemas import (
    ActionResult,
    AgentAction,
    AgentRun,
    AgentStartRequest,
    AgentStepRecord,
    AgentStepRequest,
    AgentStepResponse,
)


class AgentError(RuntimeError):
    pass


class AgentManager:
    def __init__(self, settings: Settings, llm_client: OpenAICompatibleClient) -> None:
        self.settings = settings
        self.llm_client = llm_client
        self.runs: dict[str, AgentRun] = {}

    async def start_run(self, request: AgentStartRequest) -> AgentStepResponse:
        options = request.options
        if options.max_steps is None:
            options.max_steps = self.settings.max_agent_steps
        run = AgentRun(
            task=request.task,
            llm_config=request.llm_config,
            options=options,
            status="thinking",
        )
        self.runs[run.id] = run
        return await self._plan_next(run, request.browser_state, None)

    async def step_run(self, request: AgentStepRequest) -> AgentStepResponse:
        run = self.get_run(request.run_id)
        if run.status in {"completed", "failed", "stopped"}:
            return self._response_for_terminal(run)

        last_result = request.last_action_result
        if run.pending_action and last_result:
            run.steps.append(
                AgentStepRecord(
                    index=len(run.steps) + 1,
                    browser_state=request.browser_state,
                    action=run.pending_action,
                    result=last_result,
                    message=last_result.message or last_result.error or "Action result received.",
                )
            )
            run.pending_action = None

        if request.user_confirmation == "deny":
            run.status = "stopped"
            run.updated_at = datetime.now(timezone.utc)
            return AgentStepResponse(
                run_id=run.id,
                status=run.status,
                step_index=len(run.steps),
                message="User denied the pending action; run stopped.",
                action=None,
                requires_confirmation=False,
            )

        if len(run.steps) >= (run.options.max_steps or self.settings.max_agent_steps):
            run.status = "failed"
            run.updated_at = datetime.now(timezone.utc)
            return AgentStepResponse(
                run_id=run.id,
                status=run.status,
                step_index=len(run.steps),
                message="Reached the maximum number of steps before completing the task.",
                action=None,
                requires_confirmation=False,
                summary="达到最大步骤数，任务未完成。",
            )

        return await self._plan_next(run, request.browser_state, last_result)

    def stop_run(self, run_id: str) -> AgentStepResponse:
        run = self.get_run(run_id)
        run.status = "stopped"
        run.pending_action = None
        run.updated_at = datetime.now(timezone.utc)
        return AgentStepResponse(
            run_id=run.id,
            status=run.status,
            step_index=len(run.steps),
            message="Run stopped by user.",
            action=None,
            requires_confirmation=False,
        )

    def get_run(self, run_id: str) -> AgentRun:
        run = self.runs.get(run_id)
        if not run:
            raise AgentError(f"Run not found: {run_id}")
        return run

    async def _plan_next(
        self,
        run: AgentRun,
        browser_state,
        last_action_result: ActionResult | None,
    ) -> AgentStepResponse:
        run.status = "thinking"
        run.updated_at = datetime.now(timezone.utc)
        messages = build_messages(run, browser_state, last_action_result)

        try:
            raw_action = await self.llm_client.chat_json(messages, config=run.llm_config)
            action = AgentAction.model_validate(raw_action)
        except (LLMClientError, ValidationError) as exc:
            run.status = "failed"
            run.updated_at = datetime.now(timezone.utc)
            return AgentStepResponse(
                run_id=run.id,
                status=run.status,
                step_index=len(run.steps) + 1,
                message=f"Failed to plan next action: {exc}",
                action=None,
                requires_confirmation=False,
                summary="模型返回的动作无效或调用失败。",
            )

        action = apply_safety(action, browser_state)
        run.pending_action = action
        run.updated_at = datetime.now(timezone.utc)

        if action.type == "done":
            run.status = "completed"
            run.pending_action = None
            return AgentStepResponse(
                run_id=run.id,
                status=run.status,
                step_index=len(run.steps) + 1,
                message=action.summary or action.rationale or "Task completed.",
                action=None,
                requires_confirmation=False,
                summary=action.summary,
            )

        if action.type == "fail":
            run.status = "failed"
            run.pending_action = None
            return AgentStepResponse(
                run_id=run.id,
                status=run.status,
                step_index=len(run.steps) + 1,
                message=action.summary or action.rationale or "Task failed.",
                action=None,
                requires_confirmation=False,
                summary=action.summary,
            )

        if action.type == "ask_user" or action.requires_confirmation:
            run.status = "awaiting_confirmation"
            return AgentStepResponse(
                run_id=run.id,
                status=run.status,
                step_index=len(run.steps) + 1,
                message=action.text or action.rationale or "User confirmation required.",
                action=action,
                requires_confirmation=True,
                summary=action.summary,
            )

        run.status = "executing"
        return AgentStepResponse(
            run_id=run.id,
            status=run.status,
            step_index=len(run.steps) + 1,
            message=action.rationale or f"Execute {action.type}.",
            action=action,
            requires_confirmation=False,
            summary=action.summary,
        )

    def _response_for_terminal(self, run: AgentRun) -> AgentStepResponse:
        return AgentStepResponse(
            run_id=run.id,
            status=run.status,
            step_index=len(run.steps),
            message=f"Run is already {run.status}.",
            action=None,
            requires_confirmation=False,
        )
