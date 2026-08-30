"""Non-deterministic (semantic) approval rules -- LLM call required.

Each rule here calls a real Bedrock model to make a judgment call that a
keyword/string match cannot make reliably (the Phase 5 brief explicitly
forbids `if "dast" in text`). Structured output is enforced via Bedrock
Converse's tool-forcing (`toolChoice`), not free-text parsing -- the model
is required to call a single-purpose classification "tool", so its answer
always deserializes to the expected shape instead of relying on parsing
prose.

Same extensibility shape as deterministic.py: append a new rule function to
RULES for a future semantic condition (e.g. "is this an Argus red-team
action") without touching the interceptor or the deterministic rules.
"""

import json
import logging
import os
from dataclasses import dataclass

import boto3

logger = logging.getLogger(__name__)

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
AWS_REGION = os.environ.get("AGENT_REGION") or boto3.Session().region_name or "us-east-1"

_bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)


@dataclass
class Decision:
    decision: str  # "HITL_REQUIRED" (semantic rules never emit ALLOW/BLOCK/APPROVAL_REQUIRED)
    reason: str
    human_question: str


_DAST_CLASSIFIER_TOOL = {
    "toolSpec": {
        "name": "classify_dast_relevance",
        "description": (
            "Classify whether an MCP tool call is related to DAST (dynamic "
            "application security testing) -- running, configuring, or asking "
            "about actively scanning/testing a live API or application, as "
            "opposed to unrelated documentation topics."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "is_dast_related": {
                        "type": "boolean",
                        "description": "True if this request is semantically related to DAST.",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "One sentence explaining the classification.",
                    },
                },
                "required": ["is_dast_related", "rationale"],
            }
        },
    }
}

_DAST_SYSTEM_PROMPT = (
    "You are a security policy classifier for an internal documentation-search "
    "agent. You will be shown one MCP tool call (tool name, target, and "
    "arguments) that an AI agent is about to make. Decide, using your own "
    "semantic understanding of the request's meaning (not a keyword search), "
    "whether it is related to DAST -- dynamic application security testing: "
    "actively running, configuring, launching, or asking in detail about "
    "scanning/testing a live running API or application for vulnerabilities. "
    "General API-security background, documentation topics, or unrelated "
    "questions are NOT DAST-related even if they mention security. Always "
    "respond by calling the classify_dast_relevance tool -- never respond in "
    "plain text."
)


def _classify_dast(request: dict) -> tuple[bool, str]:
    user_content = json.dumps(
        {
            "method": request["method"],
            "tool_name": request["tool_name"],
            "target": request["target"],
            "arguments": request["arguments"],
        }
    )
    response = _bedrock.converse(
        modelId=MODEL_ID,
        system=[{"text": _DAST_SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": user_content}]}],
        toolConfig={
            "tools": [_DAST_CLASSIFIER_TOOL],
            "toolChoice": {"tool": {"name": "classify_dast_relevance"}},
        },
    )

    for block in response["output"]["message"]["content"]:
        tool_use = block.get("toolUse")
        if tool_use and tool_use.get("name") == "classify_dast_relevance":
            classification = tool_use["input"]
            return bool(classification["is_dast_related"]), str(classification.get("rationale", ""))

    raise RuntimeError(f"model did not return the expected classify_dast_relevance tool call: {response}")


def _rule_dast_requires_hitl(request: dict) -> Decision | None:
    """Any call semantically related to DAST requires human intervention.

    This is intentionally non-deterministic: the Approval Agent's LLM makes
    the call, not a keyword match, so paraphrases and indirect requests are
    caught the same way an explicit "DAST" mention would be.
    """
    is_dast_related, rationale = _classify_dast(request)
    logger.info(json.dumps({"decision_mode": "semantic", "llm_invoked": True, "is_dast_related": is_dast_related}))
    if not is_dast_related:
        return None
    return Decision(
        decision="HITL_REQUIRED",
        reason=f"semantically classified as DAST-related: {rationale}",
        human_question=(
            f"This request looks DAST-related ({rationale}). Approve, deny, or "
            f"give additional instructions before it proceeds? Tool="
            f"{request['tool_name']!r}, arguments={request['arguments']!r}."
        ),
    )


# Ordered list of semantic rules. Evaluated top to bottom; the first match
# wins. Each rule call here is a real LLM invocation -- keep this list short.
RULES = [_rule_dast_requires_hitl]


def evaluate(request: dict) -> Decision | None:
    """Return the first matching semantic rule's Decision, or None if no
    semantic rule applies (caller should default to ALLOW)."""
    for rule in RULES:
        decision = rule(request)
        if decision is not None:
            return decision
    return None
