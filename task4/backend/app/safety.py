from __future__ import annotations

from urllib.parse import urlparse

from app.schemas import AgentAction, BrowserElement, BrowserState

DANGEROUS_WORDS = {
    "submit",
    "send",
    "post",
    "publish",
    "delete",
    "remove",
    "pay",
    "payment",
    "purchase",
    "buy",
    "order",
    "checkout",
    "confirm",
    "transfer",
    "withdraw",
    "deposit",
    "authorize",
    "allow",
    "grant",
    "login",
    "sign in",
    "sign up",
    "register",
    "password",
    "upload",
    "download",
    "unsubscribe",
    "close account",
}

SENSITIVE_HOST_HINTS = {
    "bank",
    "paypal",
    "stripe",
    "checkout",
    "wallet",
    "health",
    "medical",
    "gov",
    "tax",
}


def apply_safety(action: AgentAction, state: BrowserState) -> AgentAction:
    if action.type in {"done", "fail", "ask_user", "read_page", "wait", "scroll"}:
        return action

    if action.type in {"close_tab"}:
        action.requires_confirmation = True
        return action

    target = find_element(state, action.target_element_id)
    searchable = " ".join(
        part.lower()
        for part in [
            action.type,
            action.rationale,
            action.text,
            action.key,
            target.text if target else None,
            target.aria_label if target else None,
            target.placeholder if target else None,
            target.type if target else None,
            target.tag if target else None,
            state.url,
        ]
        if part
    )

    if any(word in searchable for word in DANGEROUS_WORDS):
        action.requires_confirmation = True

    if target and target.type and target.type.lower() in {"password", "file", "submit"}:
        action.requires_confirmation = True

    host = urlparse(state.url).hostname or ""
    if action.type in {"click", "type", "clear", "press_key", "select"} and any(
        hint in host.lower() for hint in SENSITIVE_HOST_HINTS
    ):
        action.requires_confirmation = True

    return action


def find_element(state: BrowserState, element_id: str | None) -> BrowserElement | None:
    if not element_id:
        return None
    for element in state.elements:
        if element.id == element_id:
            return element
    return None
