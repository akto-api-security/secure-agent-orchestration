"""Local unit tests for handler.py.

Run with the real bundled OPA binary (see README.md "Test locally"):

    OPA_BIN_PATH=./bin/opa python -m pytest tests/ -v

These exercise the full Lambda handler -> subprocess -> OPA path for the
baseline layer, not a mocked policy decision. The Approval Agent hop
(handler._call_approval_agent) is monkeypatched -- it's a real AgentCore
Runtime invocation over the network in production, which unit tests have no
business making; approval-agent/tests/ covers that service's own logic.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("APPROVAL_AGENT_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/fake")

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


def test_tools_list_is_allowed_without_calling_approval_agent(monkeypatch):
    def _fail(*_args, **_kwargs):
        raise AssertionError("tools/list must not consult the Approval Agent")

    monkeypatch.setattr(h, "_call_approval_agent", _fail)
    result = h.handler(_event("tools/list"), None)
    assert "transformedGatewayRequest" in result["mcp"]
    assert "transformedGatewayResponse" not in result["mcp"]


def test_search_documentation_allowed_by_approval_agent(monkeypatch):
    monkeypatch.setattr(
        h, "_call_approval_agent", lambda payload: {"decision": "ALLOW", "decision_mode": "deterministic", "llm_invoked": False}
    )
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


def test_send_feedback_requires_approval(monkeypatch):
    monkeypatch.setattr(
        h,
        "_call_approval_agent",
        lambda payload: {
            "decision": "APPROVAL_REQUIRED",
            "decision_mode": "deterministic",
            "llm_invoked": False,
            "approval_id": "appr-123",
            "human_question": "Approve sendFeedback?",
        },
    )
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
    assert response["body"]["error"]["code"] == -32010
    assert response["body"]["error"]["data"]["reference_id"] == "appr-123"


def test_dast_query_requires_hitl(monkeypatch):
    monkeypatch.setattr(
        h,
        "_call_approval_agent",
        lambda payload: {
            "decision": "HITL_REQUIRED",
            "decision_mode": "semantic",
            "llm_invoked": True,
            "hitl_id": "hitl-456",
            "human_question": "This looks DAST-related -- proceed?",
        },
    )
    event = _event(
        "tools/call",
        tool_name="mac-akto-api-mcp___searchDocumentation",
        arguments={"query": "Run a DAST scan against this API"},
    )
    result = h.handler(event, None)
    response = result["mcp"]["transformedGatewayResponse"]
    assert response["body"]["error"]["code"] == -32011
    assert response["body"]["error"]["data"]["reference_id"] == "hitl-456"


def test_approval_agent_block_is_enforced(monkeypatch):
    monkeypatch.setattr(
        h,
        "_call_approval_agent",
        lambda payload: {"decision": "BLOCK", "reason": "invalid grant", "decision_mode": "grant_verification", "llm_invoked": False},
    )
    event = _event(
        "tools/call",
        tool_name="mac-akto-api-mcp___sendFeedback",
        arguments={"feedback": "test", "_asl_grant": "bogus"},
    )
    result = h.handler(event, None)
    response = result["mcp"]["transformedGatewayResponse"]
    assert response["body"]["error"]["code"] == -32001


def test_approval_agent_payload_carries_action_authorize(monkeypatch):
    # Regression test: a real Approval Agent dispatches on a required
    # 'action' field (see approval-agent/main.py) -- this was once missing
    # from the interceptor's outgoing payload entirely, and neither side's
    # own unit tests (each mocking across this exact boundary) caught it.
    # Only a live end-to-end test surfaced it, so this is now covered here.
    seen_payloads = []

    def _capture(payload):
        seen_payloads.append(payload)
        return {"decision": "ALLOW", "decision_mode": "deterministic", "llm_invoked": False}

    monkeypatch.setattr(h, "_call_approval_agent", _capture)
    event = _event("tools/call", tool_name="mac-akto-api-mcp___searchDocumentation", arguments={"query": "x"})
    h.handler(event, None)
    assert seen_payloads[0]["action"] == "authorize"


def test_grant_argument_is_stripped_before_forwarding_on_allow(monkeypatch):
    seen_payloads = []

    def _capture(payload):
        seen_payloads.append(payload)
        return {"decision": "ALLOW", "decision_mode": "grant_verification", "llm_invoked": False}

    monkeypatch.setattr(h, "_call_approval_agent", _capture)
    event = _event(
        "tools/call",
        tool_name="mac-akto-api-mcp___sendFeedback",
        arguments={"feedback": "test", "_asl_grant": "signed-token"},
    )
    result = h.handler(event, None)
    forwarded_args = result["mcp"]["transformedGatewayRequest"]["body"]["params"]["arguments"]
    assert "_asl_grant" not in forwarded_args
    assert seen_payloads[0]["grant"] == "signed-token"
    assert "_asl_grant" not in seen_payloads[0]["arguments"]


def test_approval_agent_failure_fails_closed(monkeypatch):
    def _raise(payload):
        raise h.ApprovalAgentError("network error")

    monkeypatch.setattr(h, "_call_approval_agent", _raise)
    event = _event("tools/call", tool_name="mac-akto-api-mcp___searchDocumentation", arguments={"query": "x"})
    result = h.handler(event, None)
    response = result["mcp"]["transformedGatewayResponse"]
    assert response["body"]["error"]["code"] == -32000


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
