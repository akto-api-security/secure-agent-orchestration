"""SigV4-authenticated calls to the AgentCore Gateway, scoped to the
mac-akto-api-mcp MCP target (Akto API Security / DAST documentation).

The Gateway's inbound authorizer is AWS_IAM, the same mechanism already
verified with `awscurl`. This module re-implements that signing with
botocore directly, since the running agent container only carries its
AgentCore Runtime execution-role credentials (no `awscurl` available), and
resolves those credentials from the default boto3 credential chain.

Every tool the Gateway lists for this target is discovered and exposed to
the agent's LLM via Strands' native `MCPAgentTool` adapter, including
sendFeedback -- safe because OPA and the Approval Agent still gate
sendFeedback execution regardless of what the LLM can see. Target isolation
is maintained by only keeping tools namespaced under TARGET_PREFIX; this
agent structurally cannot see or call the other MCP target's tools.

The interceptor may also return APPROVAL_REQUIRED/HITL_REQUIRED instead of
a plain ALLOW/BLOCK; GatewayApprovalHook (below) converts that into a real
Strands interrupt until a human decision resumes it. This module and the
LLM itself never decide who needs approval -- that decision is made
entirely by the interceptor + Approval Agent; this file only reacts to it
mechanically.
"""

import asyncio
import itertools
import json
import logging
import os
from datetime import timedelta
from typing import Any

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from mcp.types import Tool as MCPTool
from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent, HookProvider, HookRegistry
from strands.tools.mcp import MCPAgentTool

logger = logging.getLogger(__name__)

GATEWAY_URL = os.environ["GATEWAY_URL"]
GATEWAY_REGION = os.environ.get("GATEWAY_REGION") or boto3.Session().region_name or "us-east-1"
TARGET_PREFIX = os.environ.get("MCP_TARGET_PREFIX", "mac-akto-api-mcp")

# Interceptor error codes for a pending human decision (see
# interceptor/handler.py's _DECISION_CODES). -32001 (BLOCK) and -32000
# (fail-closed) are pre-existing codes and are NOT treated as markers --
# they're terminal errors, not something to pause and resume.
_PENDING_DECISION_CODES = {-32010: "APPROVAL_REQUIRED", -32011: "HITL_REQUIRED"}
_ASL_MARKER_KEY = "asl_decision"

# Reserved argument key the interceptor recognizes on a retried tools/call
# (see interceptor/handler.py GRANT_ARG_KEY) -- stripped before the real MCP
# target ever sees it.
_GRANT_ARG_KEY = "_asl_grant"
_INTERRUPT_NAME = "gateway_authorization"

_request_ids = itertools.count(1)
_discovered_tools: list[MCPAgentTool] | None = None


def _sigv4_post(payload: dict) -> dict:
    method = payload.get("method", "?")
    logger.debug("Gateway request: method=%s id=%s", method, payload.get("id"))
    body = json.dumps(payload)
    request = AWSRequest(
        method="POST",
        url=GATEWAY_URL,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    credentials = boto3.Session().get_credentials()
    SigV4Auth(credentials, "bedrock-agentcore", GATEWAY_REGION).add_auth(request)
    response = requests.post(GATEWAY_URL, data=body, headers=dict(request.headers), timeout=30)
    logger.info("Gateway response: method=%s status=%d", method, response.status_code)
    response.raise_for_status()
    return response.json()


class _GatewayToolClient:
    """Duck-typed stand-in for strands.tools.mcp.MCPClient, implementing only
    the call_tool_async contract MCPAgentTool.stream() actually calls. The
    real MCPClient speaks MCP over stdio/SSE/streamable-HTTP transports, none
    of which support this Gateway's AWS_IAM (SigV4) inbound authorizer -- so
    each call is routed through this project's own SigV4-signed HTTP POST
    (_sigv4_post) instead of a real MCP ClientSession.
    """

    def __init__(self, namespaced_tool_name: str) -> None:
        self._namespaced_tool_name = namespaced_tool_name

    async def call_tool_async(
        self,
        tool_use_id: str,
        name: str,
        arguments: dict[str, Any] | None = None,
        read_timeout_seconds: timedelta | None = None,
        meta: dict[str, Any] | None = None,
        progress_callback: Any = None,
        *,
        cancel_signal: Any = None,
    ) -> dict:
        del name, read_timeout_seconds, meta, progress_callback, cancel_signal  # part of MCPClient's contract, unused here
        try:
            result = await asyncio.to_thread(
                _sigv4_post,
                {
                    "jsonrpc": "2.0",
                    "id": next(_request_ids),
                    "method": "tools/call",
                    "params": {"name": self._namespaced_tool_name, "arguments": arguments or {}},
                },
            )
        except requests.RequestException as exc:
            logger.warning("Gateway request failed for tool=%s: %s", self._namespaced_tool_name, exc)
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": f"Gateway request failed: {exc}"}],
            }

        if "error" in result:
            error = result["error"]
            code = error.get("code")
            if code in _PENDING_DECISION_CODES:
                data = error.get("data") or {}
                marker = {
                    _ASL_MARKER_KEY: _PENDING_DECISION_CODES[code],
                    "reference_id": data.get("reference_id"),
                    "human_question": data.get("human_question", ""),
                    "tool_name": self._namespaced_tool_name,
                    "arguments": arguments or {},
                }
                logger.info(
                    "Gateway/MCP returned %s for tool=%s: reference_id=%s",
                    _PENDING_DECISION_CODES[code], self._namespaced_tool_name, marker["reference_id"],
                )
                return {"toolUseId": tool_use_id, "status": "error", "content": [{"text": json.dumps(marker)}]}

            message = error.get("message", error)
            logger.info("Gateway/MCP returned an error for tool=%s: %s", self._namespaced_tool_name, message)
            return {"toolUseId": tool_use_id, "status": "error", "content": [{"text": str(message)}]}

        content = result.get("result", {}).get("content", [])
        text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
        text = "\n\n".join(text_parts) if text_parts else json.dumps(result.get("result", result))
        logger.info("Tool call succeeded: tool=%s, %d chars returned", self._namespaced_tool_name, len(text))
        return {"toolUseId": tool_use_id, "status": "success", "content": [{"text": text}]}


class GatewayApprovalHook(HookProvider):
    """Converts an interceptor APPROVAL_REQUIRED/HITL_REQUIRED marker into a
    real Strands interrupt, and a human's resumed decision back into either
    a grant-bearing retry, a cancellation, or a surfaced instruction.

    This hook owns none of the approval/HITL business logic -- it never
    decides whether a tool call needs a human, only reacts to the
    interceptor + Approval Agent's own decision. State is per-Agent (one
    GatewayApprovalHook instance per A2A context_id, since build_agent()
    constructs a fresh Agent+hook per context), so concurrent conversations
    never share pending-marker state.

    Mechanics (built from Strands' real interrupt/retry primitives and the
    A2A input-required task state):
      1. A tool call comes back with an asl_decision marker (AfterToolCallEvent) ->
         stash it, set retry=True (discard this result, re-invoke the same
         tool_use once more -- no second real Gateway call happens yet).
      2. The retry's BeforeToolCallEvent sees the stashed marker -> calls
         event.interrupt(), which raises and pauses the whole agent turn
         (StrandsA2AExecutor maps this to A2A task state input_required).
         No tool dispatch happens on this pass either.
      3. When a human's decision resumes the task, the SAME
         BeforeToolCallEvent callback runs again; event.interrupt() this
         time returns the decision instead of raising:
           - deny -> event.cancel_tool = ... (tool never actually dispatches)
           - instruction -> event.cancel_tool = ... (instruction text becomes
             the tool's result content, so the running LLM sees it in the
             same continued turn and can choose to retry with adjusted
             arguments -- a fresh tool_use, evaluated fresh)
           - approve -> event.tool_use is mutated to attach the signed grant,
             and the tool call proceeds normally: exactly one real Gateway
             dispatch happens (the retry, now carrying the grant) -- the
             original attempt never reached MCP, so nothing executes twice.
    """

    def __init__(self) -> None:
        self._pending: dict[str, dict] = {}

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(AfterToolCallEvent, self._after_tool_call)
        registry.add_callback(BeforeToolCallEvent, self._before_tool_call)

    def _after_tool_call(self, event: AfterToolCallEvent) -> None:
        result = event.result
        if not isinstance(result, dict) or result.get("status") != "error":
            return
        content = result.get("content") or []
        if not content or "text" not in content[0]:
            return
        try:
            marker = json.loads(content[0]["text"])
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(marker, dict) or _ASL_MARKER_KEY not in marker:
            return

        tool_use_id = event.tool_use["toolUseId"]
        self._pending[tool_use_id] = marker
        logger.info(
            "Pausing for human decision: tool_use_id=%s decision=%s reference_id=%s",
            tool_use_id, marker[_ASL_MARKER_KEY], marker.get("reference_id"),
        )
        event.retry = True

    def _before_tool_call(self, event: BeforeToolCallEvent) -> None:
        tool_use_id = event.tool_use["toolUseId"]
        marker = self._pending.get(tool_use_id)
        if marker is None:
            return  # nothing pending for this tool call -- dispatch normally

        response = event.interrupt(_INTERRUPT_NAME, reason=marker)
        # Only reached on resume -- the first call above raises InterruptException.
        del self._pending[tool_use_id]

        decision = response.get("decision") if isinstance(response, dict) else None
        if decision == "deny":
            event.cancel_tool = response.get("message") or "Denied by human reviewer."
        elif decision == "instruction":
            instruction_text = response.get("instruction_text", "")
            event.cancel_tool = (
                f"A human reviewed this and did not approve automatic execution. "
                f"Human guidance: {instruction_text!r}. Incorporate this guidance "
                f"before deciding whether and how to proceed."
            )
        elif decision == "approve":
            grant = response.get("grant")
            if not grant:
                event.cancel_tool = "Approval was reported but no grant was provided -- treating as denied."
            else:
                new_input = dict(event.tool_use.get("input") or {})
                new_input[_GRANT_ARG_KEY] = grant
                event.tool_use = {**event.tool_use, "input": new_input}
                # No cancel_tool set -- the tool dispatches normally now,
                # this time carrying the grant for the interceptor to verify.
        else:
            event.cancel_tool = f"Unrecognized human decision {decision!r} -- treating as denied."


def discover_gateway_tools() -> list[MCPAgentTool]:
    """Discover every tool the Gateway lists for this agent's own MCP target
    and expose each one to the LLM via MCPAgentTool -- no restriction to a
    single read-only search tool. Cross-target tools are excluded by the
    TARGET_PREFIX namespace filter, not invented, and not modified from what
    the Gateway's own tools/list response actually returns.
    """
    global _discovered_tools
    if _discovered_tools is not None:
        return _discovered_tools

    listing = _sigv4_post({"jsonrpc": "2.0", "id": next(_request_ids), "method": "tools/list"})
    tools = listing.get("result", {}).get("tools", [])
    scoped = [t for t in tools if t.get("name", "").startswith(f"{TARGET_PREFIX}___")]
    if not scoped:
        raise RuntimeError(f"Gateway returned no tools for target '{TARGET_PREFIX}'")

    discovered = []
    for t in scoped:
        namespaced_name = t["name"]
        bare_name = namespaced_name.partition("___")[2]
        mcp_tool = MCPTool(
            name=bare_name,
            description=t.get("description") or f"Akto Gateway tool {bare_name}",
            inputSchema=t.get("inputSchema") or {"type": "object", "properties": {}},
        )
        discovered.append(MCPAgentTool(mcp_tool=mcp_tool, mcp_client=_GatewayToolClient(namespaced_name)))

    logger.info(
        "Discovered %d Gateway tool(s) for target=%s: %s",
        len(discovered),
        TARGET_PREFIX,
        [t.tool_name for t in discovered],
    )
    _discovered_tools = discovered
    return discovered
