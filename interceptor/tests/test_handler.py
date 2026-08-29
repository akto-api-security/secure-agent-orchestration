"""Local unit tests for handler.py.

Run with the real bundled OPA binary (see README.md "Test locally"):

    OPA_BIN_PATH=./bin/opa python -m pytest tests/ -v

These exercise the full Lambda handler -> subprocess -> OPA path, not a
mocked policy decision, so a passing run is real evidence the Rego policy
and the handler's input/output shaping agree with each other.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import handler as h  # noqa: E402


def _event(method, tool_name=None, request_id=1, arguments=None):
    body = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if tool_name is not None:
        body["params"] = {"name": tool_name, "arguments": arguments or {}}
    return {
        "interceptorInputVersion": "1.0",
        "mcp": {
            "rawGatewayRequest": {"body": ""},
            "gatewayRequest": {
                "path": "/mcp",
                "httpMethod": "POST",
                "body": body,
            },
        },
    }


def _opa_available():
    return os.path.exists(h.OPA_BIN_PATH)


pytestmark = pytest.mark.skipif(
    not _opa_available(),
    reason="bin/opa not present -- run build.sh / README 'Get the OPA binary' first",
)


def test_tools_list_is_allowed():
    result = h.handler(_event("tools/list"), None)
    assert "transformedGatewayRequest" in result["mcp"]
    assert "transformedGatewayResponse" not in result["mcp"]


def test_search_documentation_is_allowed():
    event = _event(
        "tools/call",
        tool_name="mac-akto-api-mcp___searchDocumentation",
        arguments={"query": "OWASP API security"},
    )
    result = h.handler(event, None)
    assert "transformedGatewayRequest" in result["mcp"]
    assert result["mcp"]["transformedGatewayRequest"]["body"]["params"]["name"] == (
        "mac-akto-api-mcp___searchDocumentation"
    )


def test_send_feedback_is_blocked():
    event = _event(
        "tools/call",
        tool_name="mac-akto-api-mcp___sendFeedback",
        request_id=42,
        arguments={"feedback": "test"},
    )
    result = h.handler(event, None)
    response = result["mcp"]["transformedGatewayResponse"]
    assert response["statusCode"] == 200
    assert response["body"]["id"] == 42
    assert response["body"]["error"]["code"] == -32001
    assert "sendFeedback" in response["body"]["error"]["data"]["reason"]


def test_send_feedback_blocked_on_either_target():
    event = _event("tools/call", tool_name="mac-akto-ai-mcp___sendFeedback")
    result = h.handler(event, None)
    assert "transformedGatewayResponse" in result["mcp"]


def test_malformed_event_fails_closed():
    result = h.handler({"not_mcp": {}}, None)
    response = result["mcp"]["transformedGatewayResponse"]
    assert response["body"]["error"]["code"] == -32000
    assert "fail-closed" in response["body"]["error"]["data"]["reason"]


def test_missing_request_body_fails_closed():
    event = {"interceptorInputVersion": "1.0", "mcp": {"gatewayRequest": {}}}
    result = h.handler(event, None)
    response = result["mcp"]["transformedGatewayResponse"]
    assert response["body"]["error"]["code"] == -32000
