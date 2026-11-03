from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI记事本"
    database_url: str = "sqlite:///./ai_notebook.db"

    # Anthropic-compatible API settings. `anthropic_model` is the app-specific
    # override; if omitted, the app also accepts Claude Code's
    # ANTHROPIC_DEFAULT_OPUS_MODEL environment variable.
    anthropic_model: str | None = None
    anthropic_default_opus_model: str | None = None
    anthropic_api_key: str | None = None
    anthropic_auth_token: str | None = None
    anthropic_base_url: str | None = None
    anthropic_max_tokens: int = 2048
    anthropic_effort: str = "medium"
    anthropic_enable_claude_params: bool | None = None
    api_timeout_ms: int = 600000

    reminder_poll_seconds: int = 10

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def resolved_anthropic_model(self) -> str:
        return self.anthropic_model or self.anthropic_default_opus_model or "claude-opus-4-8"

    @property
    def anthropic_timeout_seconds(self) -> float:
        return self.api_timeout_ms / 1000

    @property
    def use_claude_params(self) -> bool:
        if self.anthropic_enable_claude_params is not None:
            return self.anthropic_enable_claude_params
        return self.resolved_anthropic_model.startswith("claude-")


@lru_cache
def get_settings() -> Settings:
    return Settings()
