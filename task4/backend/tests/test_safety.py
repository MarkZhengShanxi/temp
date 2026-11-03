from app.safety import apply_safety
from app.schemas import AgentAction, BrowserElement, BrowserState


def state_with_button(text="Search", element_type=None, url="https://example.com"):
    return BrowserState(
        url=url,
        title="Test",
        elements=[
            BrowserElement(
                id="e1",
                tag="button",
                type=element_type,
                text=text,
                visible=True,
                enabled=True,
            )
        ],
    )


def test_safe_click_does_not_require_confirmation():
    action = AgentAction(type="click", target_element_id="e1", rationale="Open search")
    checked = apply_safety(action, state_with_button())
    assert checked.requires_confirmation is False


def test_delete_click_requires_confirmation():
    action = AgentAction(type="click", target_element_id="e1", rationale="Delete item")
    checked = apply_safety(action, state_with_button("Delete"))
    assert checked.requires_confirmation is True


def test_submit_button_requires_confirmation():
    action = AgentAction(type="click", target_element_id="e1", rationale="Submit form")
    checked = apply_safety(action, state_with_button("Submit", "submit"))
    assert checked.requires_confirmation is True


def test_sensitive_host_requires_confirmation_for_typing():
    action = AgentAction(type="type", target_element_id="e1", rationale="Fill amount", text="100")
    checked = apply_safety(action, state_with_button("Amount", url="https://bank.example.com"))
    assert checked.requires_confirmation is True
