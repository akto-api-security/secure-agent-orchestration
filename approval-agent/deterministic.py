"""Deterministic approval rules -- no LLM call, ever.

Each rule is a plain function of the request; the first one that returns a
non-None Decision wins. Adding a future rule (Argus, Atlas, a new
high-risk tool) means appending one function here -- the interceptor never
changes (see docs/phase-context/phase-5-context.md, "Future extensibility").
"""

from dataclasses import dataclass


@dataclass
class Decision:
    decision: str  # "APPROVAL_REQUIRED" (deterministic rules never emit ALLOW/BLOCK/HITL_REQUIRED)
    reason: str
    human_question: str


def _rule_send_feedback_requires_approval(request: dict) -> Decision | None:
    """sendFeedback always requires human approval, on either MCP target.

    This is the Phase 5 brief's own worked example of a deterministic rule:
    a fixed tool/action -> approval mapping, decided purely by tool
    identity, never by reasoning about content.
    """
    if request["bare_tool_name"] != "sendFeedback":
        return None
    return Decision(
        decision="APPROVAL_REQUIRED",
        reason="sendFeedback always requires human approval (deterministic rule, no LLM)",
        human_question=(
            f"Approve sendFeedback on target={request['target']!r} "
            f"with arguments={request['arguments']!r}?"
        ),
    )


# Ordered list of deterministic rules. Evaluated top to bottom; the first
# match wins. Append future rules here.
RULES = [_rule_send_feedback_requires_approval]


def evaluate(request: dict) -> Decision | None:
    """Return the first matching deterministic rule's Decision, or None if
    no deterministic rule applies (caller should fall through to the
    semantic rules in semantic.py)."""
    for rule in RULES:
        decision = rule(request)
        if decision is not None:
            return decision
    return None
