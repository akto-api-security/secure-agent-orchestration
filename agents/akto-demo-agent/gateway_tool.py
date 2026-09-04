"""SigV4-authenticated MCP calls to the inner AgentCore Gateway."""

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
TARGET_PREFIX = os.environ.get("MCP_TARGET_PREFIX", "")
MCP_PROTOCOL_VERSION = "2025-11-25"

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
        headers={
            "Content-Type": "application/json",
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        },
    )
    credentials = boto3.Session().get_credentials()
    SigV4Auth(credentials, "bedrock-agentcore", GATEWAY_REGION).add_auth(request)
    response = requests.post(GATEWAY_URL, data=body, headers=dict(request.headers), timeout=30)
    logger.info("Gateway response: method=%s status=%d", method, response.status_code)
    response.raise_for_status()
    return response.json()


class _GatewayToolClient:
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
        del name, read_timeout_seconds, meta, progress_callback, cancel_signal
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
            message = error.get("message", error)
            logger.info("Gateway/MCP returned an error for tool=%s: %s", self._namespaced_tool_name, message)
            return {"toolUseId": tool_use_id, "status": "error", "content": [{"text": str(message)}]}

        content = result.get("result", {}).get("content", [])
        text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
        text = "\n\n".join(text_parts) if text_parts else json.dumps(result.get("result", result))
        logger.info("Tool call succeeded: tool=%s, %d chars returned", self._namespaced_tool_name, len(text))
        return {"toolUseId": tool_use_id, "status": "success", "content": [{"text": text}]}


def _keep_tool(namespaced_name: str) -> bool:
    if not TARGET_PREFIX or TARGET_PREFIX == "*":
        return True
    return namespaced_name.startswith(f"{TARGET_PREFIX}___")


def discover_gateway_tools() -> list[MCPAgentTool]:
    global _discovered_tools
    if _discovered_tools is not None:
        return _discovered_tools

    listing = _sigv4_post({"jsonrpc": "2.0", "id": next(_request_ids), "method": "tools/list"})
    tools = listing.get("result", {}).get("tools", [])
    scoped = [t for t in tools if _keep_tool(t.get("name", ""))]
    if not scoped:
        raise RuntimeError(f"Gateway returned no tools (prefix={TARGET_PREFIX!r})")

    discovered = []
    for t in scoped:
        namespaced_name = t["name"]
        bare_name = namespaced_name.partition("___")[2] or namespaced_name
        mcp_tool = MCPTool(
            name=bare_name,
            description=t.get("description") or f"Gateway tool {bare_name}",
            inputSchema=t.get("inputSchema") or {"type": "object", "properties": {}},
        )
        discovered.append(MCPAgentTool(mcp_tool=mcp_tool, mcp_client=_GatewayToolClient(namespaced_name)))

    logger.info(
        "Discovered %d Gateway tool(s) prefix=%s: %s",
        len(discovered),
        TARGET_PREFIX or "*",
        [t.tool_name for t in discovered],
    )
    _discovered_tools = discovered
    return discovered
