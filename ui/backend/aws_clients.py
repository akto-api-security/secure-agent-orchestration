"""Thin boto3 wrappers around the two AgentCore Runtime invocations this UI
needs -- the Orchestrator and the Approval Agent. Mirrors the error-handling
shape of agents/orchestrator/a2a_client.py's `_invoke` (ClientError/
BotoCoreError -> one typed exception the API layer turns into a clean JSON
error), but calls the Orchestrator's plain HTTP-protocol entrypoint
(`{"prompt": ...}` / `{"resume_token": ...}`) rather than treating it as an
A2A peer.

This module never calls the Gateway or MCP -- only the Orchestrator and
Approval Agent runtimes, both already reachable via the existing standalone
asl-orchestrator-invoke-<env> / asl-approval-agent-invoke-<env> IAM
policies.
"""

import json
import logging

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from .config import settings

logger = logging.getLogger(__name__)

_CLIENT_CONFIG = Config(connect_timeout=10, read_timeout=90, retries={"max_attempts": 1})
_client = boto3.client("bedrock-agentcore", region_name=settings.region, config=_CLIENT_CONFIG)


class AgentInvokeError(Exception):
    """Raised for any failure to get a usable response from a runtime invoke."""


def _invoke(runtime_arn: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    try:
        response = _client.invoke_agent_runtime(agentRuntimeArn=runtime_arn, payload=body)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        raise AgentInvokeError(f"invoke_agent_runtime failed ({error_code}): {exc}") from exc
    except BotoCoreError as exc:
        raise AgentInvokeError(f"invoke_agent_runtime failed: {exc}") from exc

    raw = response["response"].read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentInvokeError(f"Runtime returned malformed JSON: {exc}") from exc


def ask_orchestrator(prompt: str) -> dict:
    """Fresh request -- matches agents/orchestrator/main.py's `invoke()`
    payload contract exactly (`{"prompt": "..."}`)."""
    if not settings.orchestrator_arn:
        raise AgentInvokeError("ORCHESTRATOR_ARN is not resolved -- set the env var or run from a checkout with terraform output available.")
    return _invoke(settings.orchestrator_arn, {"prompt": prompt})


def resume_orchestrator(resume_token: dict) -> dict:
    """Continues a paused delegation -- matches main.py's
    `{"resume_token": {...}}` contract. The orchestrator itself looks up
    what the human decided (via the Approval Agent's get_decision) --
    callers here must have already recorded a decision via decide()."""
    if not settings.orchestrator_arn:
        raise AgentInvokeError("ORCHESTRATOR_ARN is not resolved.")
    return _invoke(settings.orchestrator_arn, {"resume_token": resume_token})


def decide(reference_id: str, decision: str, instruction_text: str | None = None, approver: str = "demo-ui") -> dict:
    """Records a human decision -- matches approval-agent/main.py's
    `decide` action contract (the same one scripts/approval_decide.py and
    demo_interactive.sh already use)."""
    if not settings.approval_agent_arn:
        raise AgentInvokeError("APPROVAL_AGENT_ARN is not resolved.")
    payload = {"action": "decide", "reference_id": reference_id, "decision": decision, "approver": approver}
    if instruction_text:
        payload["instruction_text"] = instruction_text
    return _invoke(settings.approval_agent_arn, payload)
