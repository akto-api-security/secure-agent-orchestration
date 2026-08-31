"""Request/response mapping for the Akto Guardrail Engine's evaluate endpoint.

This is the only file that should need to change if the Guardrail Engine's
wire format ever changes — everything else in this package (transport,
timeout/error handling, configuration, the public interface) is written to
be agnostic to it.
"""

import json
import re
import time as time_module
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from .models import Decision, RequestContext

# guardrails=true evaluates the request; ingest_data=true also records it
# for the dashboard. response_guardrails is omitted -- this SDK evaluates a
# tool call before it executes, so there is no response payload yet.
ENDPOINT_PATH = "/api/http-proxy?guardrails=true&ingest_data=true"
HTTP_METHOD = "GET"
CONTEXT_SOURCE = "AGENTIC"
SOURCE = "MIRRORING"
TAG = json.dumps({"source": "AGENTIC"})

# An MCP tool call has no real HTTP verb; "POST" is sent in the engine's
# generic `method` field as the closest fit (an invoked action), rather
# than inventing a marker string.
TOOL_CALL_METHOD_VALUE = "POST"

CORRELATION_ID_HEADER = "x-request-id"
SESSION_ID_HEADER = "x-session-id"

# Used as the `host` value only when RequestContext.requesting_agent isn't
# populated -- deliberately not the MCP target or tool name (see
# build_request), so a missing agent identity is visibly reported as
# missing rather than silently mislabeled as something else.
UNKNOWN_AGENT_HOST = "unknown-agent"

# The Guardrail Engine's own URL is namespaced per account, e.g.
# "https://1234567890-guardrails.akto.io" -- the leading digits are the
# account ID. Used as a fallback so a customer doesn't have to configure
# their account ID separately from the URL they already have to configure.
_ACCOUNT_ID_FROM_HOST = re.compile(r"^(\d+)-")


def _account_id_from_url(base_url: str) -> Optional[str]:
    host = urlparse(base_url).hostname or ""
    match = _ACCOUNT_ID_FROM_HOST.match(host)
    return match.group(1) if match else None


def build_request(request_context: RequestContext, config) -> Tuple[str, Dict[str, str], bytes]:
    """Build (path, headers, body_bytes) for the outbound HTTP request."""
    # The Guardrail Engine attributes this traffic to a "host" via a
    # `host` key inside requestHeaders' JSON-encoded header map, not a
    # top-level field. This must be the calling agent's own identity --
    # never the MCP target or tool name, which identify what's being
    # called, not who's calling. A missing agent identity is reported as
    # such rather than silently mislabeled as the target/tool.
    host = request_context.requesting_agent or UNKNOWN_AGENT_HOST
    request_headers = {"host": host}
    if request_context.session_id:
        request_headers[SESSION_ID_HEADER] = request_context.session_id

    target = request_context.mcp_target or "unknown-target"
    url_path = f"/mcp/{target}/{request_context.bare_tool_name}"

    body: Dict[str, Any] = {
        "path": url_path,
        "requestHeaders": json.dumps(request_headers),
        "responseHeaders": "{}",
        "method": TOOL_CALL_METHOD_VALUE,
        "requestPayload": json.dumps(request_context.to_normalized_dict()),
        "ip": "127.0.0.1",
        "destIp": "127.0.0.1",
        # Mandatory for the Guardrail Engine to record this traffic in the
        # dashboard. There's no real HTTP status yet (this SDK evaluates a
        # tool call before it executes) -- "200" is a fixed placeholder.
        "statusCode": "200",
        "status": "200",
        "time": str(int(time_module.time() * 1000)),
        "type": None,
        "akto_vxlan_id": "0",
        "is_pending": "false",
        "source": SOURCE,
        "tag": TAG,
        "contextSource": CONTEXT_SOURCE,
    }

    account_id = config.account_id or _account_id_from_url(config.base_url)
    if account_id:
        body["akto_account_id"] = account_id

    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers[config.api_key_header] = config.api_key
    headers[CORRELATION_ID_HEADER] = request_context.correlation_id

    return ENDPOINT_PATH, headers, json.dumps(body).encode("utf-8")


def parse_response(status_code: int, raw_body: bytes) -> Dict[str, Any]:
    """Parse the raw HTTP response body into this SDK's normalized fields.

    Raises ValueError on anything unexpected — client.py converts that into
    AktoGuardrailMalformedResponseError.
    """
    parsed = json.loads(raw_body)
    if not isinstance(parsed, dict):
        raise ValueError(f"expected a JSON object, got {type(parsed).__name__}")

    try:
        result = parsed["data"]["guardrailsResult"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"expected data.guardrailsResult in response, got: {parsed!r}") from exc

    if "Allowed" not in result or not isinstance(result["Allowed"], bool):
        raise ValueError(f"expected a boolean 'Allowed' field, got: {result.get('Allowed')!r}")

    decision = Decision.ALLOW if result["Allowed"] else Decision.BLOCK

    return {
        "decision": decision,
        "reason": result.get("Reason", ""),
        "reference_id": None,
        "raw": parsed,
    }
