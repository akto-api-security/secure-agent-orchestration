"""SigV4-authenticated calls to the Phase 1 AgentCore Gateway, scoped to the
mac-akto-ai-mcp MCP target (Akto Agentic Security / Atlas / Argus / MCP & A2A
security documentation).

The Gateway's inbound authorizer is AWS_IAM, the same mechanism already
verified in Phase 1 with `awscurl`. This module re-implements that signing
with botocore directly, since the running agent container only carries its
AgentCore Runtime execution-role credentials (no `awscurl` available), and
resolves those credentials from the default boto3 credential chain.

The MCP tool to call is *discovered* from the Gateway's own tools/list
response rather than hardcoded, per the Phase 2 requirement not to assume
tool names ahead of inspection.
"""

import itertools
import json
import logging
import os

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from strands import tool

logger = logging.getLogger(__name__)

GATEWAY_URL = os.environ["GATEWAY_URL"]
GATEWAY_REGION = os.environ.get("GATEWAY_REGION") or boto3.Session().region_name or "us-east-1"
TARGET_PREFIX = os.environ.get("MCP_TARGET_PREFIX", "mac-akto-ai-mcp")

_request_ids = itertools.count(1)
_resolved_tool: dict = {}


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


def _resolve_search_tool() -> tuple[str, str]:
    """Pick a safe, read-only search tool for this target from the Gateway's
    tools/list response, and identify its query argument from inputSchema."""
    if _resolved_tool:
        return _resolved_tool["name"], _resolved_tool["arg"]

    listing = _sigv4_post({"jsonrpc": "2.0", "id": next(_request_ids), "method": "tools/list"})
    tools = listing.get("result", {}).get("tools", [])
    scoped = [t for t in tools if t.get("name", "").startswith(f"{TARGET_PREFIX}___")]
    if not scoped:
        raise RuntimeError(f"Gateway returned no tools for target '{TARGET_PREFIX}'")

    read_only = [t for t in scoped if t.get("annotations", {}).get("readOnlyHint")]
    candidates = read_only or scoped
    chosen = next((t for t in candidates if "search" in t["name"].lower()), candidates[0])

    schema = chosen.get("inputSchema", {})
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    arg_name = next(
        (n for n in required if properties.get(n, {}).get("type") == "string"),
        next((n for n, p in properties.items() if p.get("type") == "string"), None),
    )
    if arg_name is None:
        raise RuntimeError(f"Gateway tool '{chosen['name']}' has no string input to query")

    _resolved_tool.update(name=chosen["name"], arg=arg_name)
    logger.info("Resolved Gateway search tool: %s (arg=%s)", chosen["name"], arg_name)
    return chosen["name"], arg_name


@tool
def search_akto_agentic_security_docs(query: str) -> str:
    """Search Akto's Agentic Security documentation for a topic and return matching results.

    Use this for any question about Atlas, Argus, agentic security, MCP
    security, A2A security, prompt injection, or how Akto tests AI agents
    and MCP servers.

    Args:
        query: The search query, e.g. a question or topic to look up in the docs.
    """
    logger.info("search_akto_agentic_security_docs called: query=%r", query)
    try:
        tool_name, arg_name = _resolve_search_tool()
        result = _sigv4_post(
            {
                "jsonrpc": "2.0",
                "id": next(_request_ids),
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": {arg_name: query}},
            }
        )
    except requests.RequestException as exc:
        logger.warning("Gateway request failed: %s", exc)
        return f"The Akto documentation search is temporarily unavailable ({exc})."
    except RuntimeError as exc:
        logger.warning("Gateway tool resolution failed: %s", exc)
        return f"The Akto documentation search could not be set up: {exc}"

    if "error" in result:
        message = result["error"].get("message", result["error"])
        logger.warning("Gateway/MCP returned an error: %s", message)
        return f"The Akto documentation search returned an error: {message}"

    content = result.get("result", {}).get("content", [])
    text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
    text = "\n\n".join(text_parts) if text_parts else json.dumps(result.get("result", result))
    logger.info("search_akto_agentic_security_docs returning %d chars via tool=%s", len(text), tool_name)
    return text
