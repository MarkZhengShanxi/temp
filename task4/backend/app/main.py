from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.agent import AgentError, AgentManager
from app.config import Settings, get_settings
from app.llm_client import LLMClientError, OpenAICompatibleClient
from app.schemas import (
    AgentStartRequest,
    AgentStepRequest,
    AgentStepResponse,
    AgentStopRequest,
    ConfigTestRequest,
    ConfigTestResponse,
)

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "backend.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE, encoding="utf-8")],
)
logger = logging.getLogger("browser_agent")

settings = get_settings()
llm_client = OpenAICompatibleClient(settings)
agent_manager = AgentManager(settings, llm_client)

app = FastAPI(title="Browser Agent Local Backend", version="0.1.0")

allow_origins = settings.cors_allowed_origins or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["content-type", "x-agent-token"],
)


def verify_token(x_agent_token: str | None = Header(default=None)) -> None:
    if settings.backend_token and x_agent_token != settings.backend_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Agent-Token.",
        )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "app": "Browser Agent Local Backend", "log_file": str(LOG_FILE)}


@app.post("/api/config/test", response_model=ConfigTestResponse, dependencies=[Depends(verify_token)])
async def test_config(request: ConfigTestRequest) -> ConfigTestResponse:
    resolved = llm_client.resolve_config(request.llm_config)
    logger.info(
        "config test requested base_url=%s model=%s api_key_present=%s",
        resolved.base_url,
        resolved.model,
        bool(resolved.api_key),
    )
    try:
        text = await llm_client.test_connection(request.llm_config)
        logger.info("config test succeeded model=%s", resolved.model)
        return ConfigTestResponse(ok=True, model=resolved.model, message=f"连接成功：{text[:80]}")
    except LLMClientError as exc:
        logger.warning("config test failed model=%s error=%s", resolved.model, exc)
        return ConfigTestResponse(ok=False, model=resolved.model, message=str(exc))


@app.post("/api/agent/start", response_model=AgentStepResponse, dependencies=[Depends(verify_token)])
async def start_agent(request: AgentStartRequest) -> AgentStepResponse:
    logger.info("agent start requested task_len=%s url=%s", len(request.task), request.browser_state.url)
    try:
        response = await agent_manager.start_run(request)
        logger.info("agent started run_id=%s status=%s", response.run_id, response.status)
        return response
    except AgentError as exc:
        logger.warning("agent start failed error=%s", exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/agent/step", response_model=AgentStepResponse, dependencies=[Depends(verify_token)])
async def step_agent(request: AgentStepRequest) -> AgentStepResponse:
    logger.info(
        "agent step requested run_id=%s last_ok=%s confirmation=%s url=%s",
        request.run_id,
        request.last_action_result.ok if request.last_action_result else None,
        request.user_confirmation,
        request.browser_state.url,
    )
    try:
        response = await agent_manager.step_run(request)
        logger.info("agent step planned run_id=%s status=%s action=%s", response.run_id, response.status, response.action.type if response.action else None)
        return response
    except AgentError as exc:
        logger.warning("agent step failed run_id=%s error=%s", request.run_id, exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/agent/stop", response_model=AgentStepResponse, dependencies=[Depends(verify_token)])
async def stop_agent(request: AgentStopRequest) -> AgentStepResponse:
    try:
        return agent_manager.stop_run(request.run_id)
    except AgentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/agent/runs/{run_id}", dependencies=[Depends(verify_token)])
async def get_run(run_id: str):
    try:
        return agent_manager.get_run(run_id)
    except AgentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
