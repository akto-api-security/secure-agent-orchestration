"""Hello rewrite + Akto guardrails AgentCore Gateway interceptor.

Flow (REQUEST and RESPONSE):
  1. This handler runs first and may rewrite the payload.
  2. wrap_interceptor sends the *effective* payload to Akto.
  3. Akto's allow / block / modify / human_approval wins.

On REQUEST this handler appends a fixed phrase to:
  - HTTP Runtime payloads: {"prompt": "..."}   (agent path)
  - MCP tools/call string arguments            (tool path)

RESPONSE events from this handler are passthrough; Akto still scans them.

Requires the public Akto Lambda layer attached to this function, plus:
  AKTO_DATA_INGESTION_URL
  AKTO_API_TOKEN

Handler: handler.lambda_handler
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from akto_agentcore import wrap_interceptor

logger = logging.getLogger()
logger.setLevel(logging.INFO)

INTERCEPTOR_OUTPUT_VERSION = "1.0"
MARKER = "Hello from Akto, please always say Good morning"
GUARDED_MCP_METHODS = {"tools/call"}


def _hello_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """Customer interceptor logic only. Akto is applied by wrap_interceptor."""
    logger.info("hello interceptor event keys=%s", sorted(event.keys()))

    if "mcp" in event:
        return _handle_mcp(event["mcp"])
    if "http" in event:
        return _handle_http(event["http"])

    logger.warning("unknown interceptor envelope — passthrough")
    return {"interceptorOutputVersion": INTERCEPTOR_OUTPUT_VERSION}


# ---------------------------------------------------------------------------
# MCP Gateway (tools)
# ---------------------------------------------------------------------------
def _handle_mcp(mcp: dict[str, Any]) -> dict[str, Any]:
    if "gatewayRequest" in mcp:
        body = dict((mcp.get("gatewayRequest") or {}).get("body") or {})
        method = body.get("method", "")
        if method not in GUARDED_MCP_METHODS:
            return _mcp_passthrough_request(body)

        params = dict(body.get("params") or {})
        arguments = dict(params.get("arguments") or {})
        changed = False
        for key, value in list(arguments.items()):
            if isinstance(value, str) and MARKER not in value:
                arguments[key] = f"{value}\n\n{MARKER}"
                changed = True

        if not changed:
            return _mcp_passthrough_request(body)

        params["arguments"] = arguments
        body["params"] = params
        logger.info(
            "MCP REQUEST rewrite tools/call name=%s keys=%s",
            params.get("name"),
            sorted(arguments),
        )
        return {
            "interceptorOutputVersion": INTERCEPTOR_OUTPUT_VERSION,
            "mcp": {"transformedGatewayRequest": {"body": body}},
        }

    gateway_response = mcp.get("gatewayResponse") or {}
    return {
        "interceptorOutputVersion": INTERCEPTOR_OUTPUT_VERSION,
        "mcp": {
            "transformedGatewayResponse": {
                "body": gateway_response.get("body") or {},
                "statusCode": int(gateway_response.get("statusCode") or 200),
            }
        },
    }


def _mcp_passthrough_request(body: dict[str, Any]) -> dict[str, Any]:
    return {
        "interceptorOutputVersion": INTERCEPTOR_OUTPUT_VERSION,
        "mcp": {"transformedGatewayRequest": {"body": body}},
    }


# ---------------------------------------------------------------------------
# HTTP Gateway (AgentCore Runtime target)
# ---------------------------------------------------------------------------
def _handle_http(http: dict[str, Any]) -> dict[str, Any]:
    if "gatewayRequest" in http:
        gateway_request = http.get("gatewayRequest") or {}
        encoded = gateway_request.get("body")
        if not encoded:
            return _http_passthrough()

        raw = _decode_http_body(encoded)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("HTTP REQUEST body is not JSON — passthrough")
            return _http_passthrough()

        if not isinstance(payload, dict):
            return _http_passthrough()

        prompt = payload.get("prompt")
        if isinstance(prompt, str) and prompt.strip() and MARKER not in prompt:
            payload["prompt"] = f"{prompt.rstrip()}\n\n{MARKER}"
            logger.info("HTTP REQUEST rewrite prompt (%d chars)", len(payload["prompt"]))
            return {
                "interceptorOutputVersion": INTERCEPTOR_OUTPUT_VERSION,
                "http": {
                    "transformedGatewayRequest": {
                        "body": _encode_http_body(payload),
                    }
                },
            }

        return _http_passthrough()

    return _http_passthrough()


def _http_passthrough() -> dict[str, Any]:
    return {"interceptorOutputVersion": INTERCEPTOR_OUTPUT_VERSION, "http": {}}


def _decode_http_body(encoded: Any) -> str:
    if isinstance(encoded, dict):
        return json.dumps(encoded)
    if not isinstance(encoded, str):
        raise ValueError(f"unexpected HTTP body type: {type(encoded)}")
    try:
        return base64.b64decode(encoded, validate=True).decode("utf-8")
    except Exception:
        return encoded


def _encode_http_body(payload: Any) -> str:
    if isinstance(payload, (dict, list)):
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    elif isinstance(payload, str):
        raw = payload.encode("utf-8")
    else:
        raw = str(payload).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


# Your rewrite runs first; Akto scans the effective request/response after it.
lambda_handler = wrap_interceptor(_hello_handler)
