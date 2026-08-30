"""A2A delegation to the Phase 2 delegated agents (API Security Agent /
Agentic Security Agent), both running on AgentCore Runtime.

Sends a standard A2A JSON-RPC `message/send` request via boto3's
`bedrock-agentcore` `invoke_agent_runtime` -- the same data-plane call
Phase 2's own README documents for testing those agents, and the same
mechanism the Terraform-created `asl-<agent>-invoke-<env>` IAM policies
exist to authorize. boto3 handles SigV4 signing itself; this module doesn't
need to hand-roll it the way `gateway_tool.py` does for the raw Gateway HTTP
endpoint in Phase 2.

Phase 5: a delegated agent's tool call may pause on an interceptor
APPROVAL_REQUIRED/HITL_REQUIRED decision, surfaced by StrandsA2AExecutor as
the real A2A task state `input-required` (confirmed against the installed
a2a-sdk's own Task/TaskStatus JSON shape, not assumed -- see
docs/phase-context/phase-5-context.md, "HITL resume mechanism"). This module
now distinguishes that state from `completed`, and can resume a parked task
by sending an `interruptResponse` DataPart on the same context/session --
the same wire contract `strands.multiagent.a2a.executor` expects. Session
affinity across the pause is provided by `runtimeSessionId` (a real,
confirmed `invoke_agent_runtime` parameter -- checked directly against the
botocore service model), which every call here now sets.
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass, field

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

# Kept distinct from AWS_REGION, which the AgentCore Runtime platform
# reserves for its own use (same reasoning Phase 2's gateway_tool.py already
# documents for GATEWAY_REGION).
AGENT_REGION = os.environ.get("AGENT_REGION") or boto3.Session().region_name or "us-east-1"

# Generous but bounded: a delegated agent call involves a Bedrock model
# invocation plus a Gateway/MCP round trip (Phase 5: now potentially also an
# Approval Agent round trip, itself possibly involving its own Bedrock model
# call for a semantic decision), so a low timeout would false-positive on
# normal latency. No retry loop -- the brief asks for basic error handling,
# not retry infrastructure.
_CLIENT_CONFIG = Config(connect_timeout=10, read_timeout=60, retries={"max_attempts": 1})

_client = boto3.client("bedrock-agentcore", region_name=AGENT_REGION, config=_CLIENT_CONFIG)


class DelegatedAgentError(Exception):
    """Raised for any failure to get a usable answer from a delegated agent."""


@dataclass
class DelegatedAgentResult:
    """Outcome of one `invoke_agent_runtime` call.

    kind is "completed" (a normal final answer, text populated) or
    "input_required" (the agent paused on a human decision -- see
    interrupts). context_id/task_id/runtime_session_id are always the
    identifiers this exact call used, so the orchestrator can persist
    exactly what a later resume call needs without any server-side session
    store of its own (see main.py's resume_token).
    """

    kind: str
    text: str
    context_id: str
    runtime_session_id: str
    task_id: str | None = None
    interrupts: list[dict] = field(default_factory=list)


def _build_a2a_request(*, question: str | None, context_id: str, task_id: str | None, interrupt_response: dict | None) -> dict:
    message = {
        "role": "user",
        "messageId": str(uuid.uuid4()),
        "contextId": context_id,
    }
    if task_id:
        message["taskId"] = task_id
    if interrupt_response is not None:
        # Wire contract expected by strands.multiagent.a2a.executor's
        # _extract_interrupt_responses: a DataPart shaped exactly like
        # Strands' own InterruptResponseContent type.
        message["parts"] = [{"kind": "data", "data": {"interruptResponse": interrupt_response}}]
    else:
        message["parts"] = [{"kind": "text", "text": question}]

    return {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {"message": message},
    }


def new_context_id(correlation_id: str) -> str:
    """A fresh A2A context_id for a brand-new request. Deterministic from
    the correlation_id purely for log correlation -- nothing depends on
    that determinism (a resume always carries the context_id explicitly via
    the resume_token, never recomputes it)."""
    return f"asl-ctx-{correlation_id}"


def new_runtime_session_id() -> str:
    """A fresh AgentCore Runtime session id. Long and random (well over
    AgentCore's documented minimum length for this field) so a resume call
    reaches the same running container/session that parked the interrupt --
    the runtimeSessionId is what provides that affinity (confirmed via the
    bedrock-agentcore botocore service model: InvokeAgentRuntime accepts
    runtimeSessionId as "the identifier of the runtime session")."""
    return f"asl-session-{uuid.uuid4()}"


def _invoke(runtime_arn: str, correlation_id: str, request_body: dict, runtime_session_id: str):
    payload = json.dumps(request_body).encode("utf-8")
    try:
        response = _client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            payload=payload,
            traceId=correlation_id,
            runtimeSessionId=runtime_session_id,
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        raise DelegatedAgentError(f"A2A call failed ({error_code}): {exc}") from exc
    except BotoCoreError as exc:
        raise DelegatedAgentError(f"A2A call failed: {exc}") from exc

    status_code = response.get("statusCode")
    logger.info(
        "[%s] Delegated agent response: runtime=%s statusCode=%s",
        correlation_id, runtime_arn, status_code,
    )

    body = response["response"].read()
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise DelegatedAgentError(f"Delegated agent returned malformed JSON: {exc}") from exc

    if "error" in result:
        raise DelegatedAgentError(f"Delegated agent returned an A2A error: {result['error']}")

    return result.get("result", {})


def _parse_task(task: dict, runtime_session_id: str) -> DelegatedAgentResult:
    status = task.get("status") or {}
    state = status.get("state")
    context_id = task.get("contextId")
    task_id = task.get("id")

    if state == "input-required":
        message = status.get("message") or {}
        parts = message.get("parts", [])
        text = "".join(p.get("text", "") for p in parts if p.get("kind") == "text")
        interrupts: list[dict] = []
        for p in parts:
            if p.get("kind") == "data":
                interrupts.extend((p.get("data") or {}).get("interrupts", []))
        if not interrupts:
            raise DelegatedAgentError("Delegated agent task is input-required but carries no interrupts")
        return DelegatedAgentResult(
            kind="input_required", text=text, context_id=context_id,
            runtime_session_id=runtime_session_id, task_id=task_id, interrupts=interrupts,
        )

    if state == "completed":
        try:
            parts = task["artifacts"][0]["parts"]
            text = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise DelegatedAgentError(
                f"Delegated agent response missing expected A2A artifact/parts shape: {exc}"
            ) from exc
        if not text.strip():
            raise DelegatedAgentError("Delegated agent returned an empty answer")
        return DelegatedAgentResult(
            kind="completed", text=text, context_id=context_id, runtime_session_id=runtime_session_id, task_id=task_id,
        )

    raise DelegatedAgentError(f"Delegated agent task ended in unexpected state: {state!r}")


def invoke_delegated_agent(runtime_arn: str, question: str, correlation_id: str) -> DelegatedAgentResult:
    """Send `question` to the delegated agent at `runtime_arn` as a brand-new
    A2A context. Raises DelegatedAgentError on any failure (unavailable
    agent, timeout, malformed response). A result with kind="input_required"
    is not a failure -- see resume_delegated_agent to continue it."""
    context_id = new_context_id(correlation_id)
    runtime_session_id = new_runtime_session_id()
    request_body = _build_a2a_request(question=question, context_id=context_id, task_id=None, interrupt_response=None)
    task = _invoke(runtime_arn, correlation_id, request_body, runtime_session_id)
    return _parse_task(task, runtime_session_id)


def resume_delegated_agent(
    runtime_arn: str,
    correlation_id: str,
    context_id: str,
    runtime_session_id: str,
    task_id: str | None,
    interrupt_id: str,
    response: dict,
) -> DelegatedAgentResult:
    """Resume a task parked in input-required, on the exact same context and
    runtime session it paused on (required for the delegated agent's
    in-memory Strands Agent -- and its interrupt state -- to still be
    there; see docs/phase-context/phase-5-context.md)."""
    request_body = _build_a2a_request(
        question=None, context_id=context_id, task_id=task_id,
        interrupt_response={"interruptId": interrupt_id, "response": response},
    )
    task = _invoke(runtime_arn, correlation_id, request_body, runtime_session_id)
    return _parse_task(task, runtime_session_id)
