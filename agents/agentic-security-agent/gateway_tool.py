"""SigV4-authenticated calls to the Phase 1 AgentCore Gateway, scoped to the
mac-akto-ai-mcp MCP target (Akto Agentic Security / Atlas / Argus / MCP & A2A
security documentation).

The Gateway's inbound authorizer is AWS_IAM, the same mechanism already
verified in Phase 1 with `awscurl`. This module re-implements that signing
with botocore directly, since the running agent container only carries its
AgentCore Runtime execution-role credentials (no `awscurl` available), and
resolves those credentials from the default boto3 credential chain.

Phase 4.1: every tool the Gateway lists for this target is discovered and
exposed to the agent's LLM via Strands' native `MCPAgentTool` adapter -- not
just a single hardcoded/filtered read-only search tool (see
docs/phase-context/phase-4-1-context.md for why that restriction existed and
why it was removed). Target isolation is maintained by only keeping tools
namespaced under TARGET_PREFIX; this agent structurally cannot see or call
the other MCP target's tools.
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
from strands.tools.mcp import MCPAgentTool

logger = logging.getLogger(__name__)

GATEWAY_URL = os.environ["GATEWAY_URL"]
GATEWAY_REGION = os.environ.get("GATEWAY_REGION") or boto3.Session().region_name or "us-east-1"
TARGET_PREFIX = os.environ.get("MCP_TARGET_PREFIX", "mac-akto-ai-mcp")

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
            message = result["error"].get("message", result["error"])
            logger.info("Gateway/MCP returned an error for tool=%s: %s", self._namespaced_tool_name, message)
            return {"toolUseId": tool_use_id, "status": "error", "content": [{"text": str(message)}]}

        content = result.get("result", {}).get("content", [])
        text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
        text = "\n\n".join(text_parts) if text_parts else json.dumps(result.get("result", result))
        logger.info("Tool call succeeded: tool=%s, %d chars returned", self._namespaced_tool_name, len(text))
        return {"toolUseId": tool_use_id, "status": "success", "content": [{"text": text}]}


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
