import anthropic

from app.config import get_settings


def create_anthropic_client() -> anthropic.Anthropic:
    """Create the official Anthropic SDK client.

    Supports both normal Anthropic credentials and Anthropic-compatible proxy
    settings such as ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL.
    """
    settings = get_settings()
    kwargs = {"timeout": settings.anthropic_timeout_seconds}
    if settings.anthropic_base_url:
        kwargs["base_url"] = settings.anthropic_base_url
    if settings.anthropic_api_key:
        kwargs["api_key"] = settings.anthropic_api_key
    if settings.anthropic_auth_token:
        kwargs["auth_token"] = settings.anthropic_auth_token
    return anthropic.Anthropic(**kwargs)
