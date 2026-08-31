"""Unit tests for AktoGuardrailClient, against a mocked HTTP transport.

No real network call is ever made — `transport` is injected.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from akto_guardrail_sdk import (  # noqa: E402
    AktoGuardrailAuthenticationError,
    AktoGuardrailClient,
    AktoGuardrailConfig,
    AktoGuardrailConfigError,
    AktoGuardrailHTTPError,
    AktoGuardrailMalformedResponseError,
    AktoGuardrailTimeoutError,
    Decision,
    RequestContext,
)
from akto_guardrail_sdk.contract import (
    CONTEXT_SOURCE,
    ENDPOINT_PATH,
    SOURCE,
    TOOL_CALL_METHOD_VALUE,
    UNKNOWN_AGENT_HOST,
)


def _config(**overrides):
    defaults = dict(base_url="https://1234567890-guardrails.example.invalid", api_key="fake-jwt", timeout_seconds=5)
    defaults.update(overrides)
    return AktoGuardrailConfig(**defaults)


def _context(**overrides):
    defaults = dict(
        correlation_id="corr-1",
        tool_name="mac-akto-api-mcp___searchDocumentation",
        bare_tool_name="searchDocumentation",
        mcp_target="mac-akto-api-mcp",
        tool_arguments={"query": "OWASP API security"},
    )
    defaults.update(overrides)
    return RequestContext(**defaults)


def _guardrails_response(allowed, reason=""):
    return {"data": {"guardrailsResult": {"Allowed": allowed, "Reason": reason}}}


def _json_transport(status_code, payload):
    def _transport(method, url, headers, body, timeout_seconds):
        return status_code, json.dumps(payload).encode("utf-8")

    return _transport


def test_allow_mapping():
    client = AktoGuardrailClient(_config(), transport=_json_transport(200, _guardrails_response(True, "clean")))
    result = client.evaluate(_context())
    assert result.decision == Decision.ALLOW
    assert result.reason == "clean"
    assert result.status_code == 200
    assert result.reference_id is None


def test_block_mapping():
    client = AktoGuardrailClient(
        _config(), transport=_json_transport(200, _guardrails_response(False, "prompt injection detected"))
    )
    result = client.evaluate(_context())
    assert result.decision == Decision.BLOCK
    assert result.reason == "prompt injection detected"


def test_malformed_json_response_raises():
    def _transport(method, url, headers, body, timeout_seconds):
        return 200, b"not json"

    client = AktoGuardrailClient(_config(), transport=_transport)
    with pytest.raises(AktoGuardrailMalformedResponseError):
        client.evaluate(_context())


def test_missing_data_wrapper_raises():
    client = AktoGuardrailClient(_config(), transport=_json_transport(200, {"success": True}))
    with pytest.raises(AktoGuardrailMalformedResponseError):
        client.evaluate(_context())


def test_missing_allowed_field_raises():
    client = AktoGuardrailClient(
        _config(), transport=_json_transport(200, {"data": {"guardrailsResult": {"Reason": "no allowed field"}}})
    )
    with pytest.raises(AktoGuardrailMalformedResponseError):
        client.evaluate(_context())


def test_non_boolean_allowed_field_raises():
    client = AktoGuardrailClient(
        _config(), transport=_json_transport(200, {"data": {"guardrailsResult": {"Allowed": "yes"}}})
    )
    with pytest.raises(AktoGuardrailMalformedResponseError):
        client.evaluate(_context())


def test_response_not_a_json_object_raises():
    def _transport(method, url, headers, body, timeout_seconds):
        return 200, json.dumps([True]).encode("utf-8")

    client = AktoGuardrailClient(_config(), transport=_transport)
    with pytest.raises(AktoGuardrailMalformedResponseError):
        client.evaluate(_context())


def test_timeout_raises():
    def _transport(method, url, headers, body, timeout_seconds):
        raise TimeoutError("timed out")

    client = AktoGuardrailClient(_config(), transport=_transport)
    with pytest.raises(AktoGuardrailTimeoutError):
        client.evaluate(_context())


def test_connection_failure_raises_http_error():
    def _transport(method, url, headers, body, timeout_seconds):
        raise OSError("connection refused")

    client = AktoGuardrailClient(_config(), transport=_transport)
    with pytest.raises(AktoGuardrailHTTPError):
        client.evaluate(_context())


def test_server_error_status_raises_http_error():
    client = AktoGuardrailClient(_config(), transport=_json_transport(500, {"error": "internal"}))
    with pytest.raises(AktoGuardrailHTTPError) as exc_info:
        client.evaluate(_context())
    assert exc_info.value.status_code == 500


def test_bad_request_status_raises_http_error():
    client = AktoGuardrailClient(_config(), transport=_json_transport(400, {"error": "malformed JSON"}))
    with pytest.raises(AktoGuardrailHTTPError) as exc_info:
        client.evaluate(_context())
    assert exc_info.value.status_code == 400


def test_auth_failure_status_raises_authentication_error():
    client = AktoGuardrailClient(_config(), transport=_json_transport(401, {}))
    with pytest.raises(AktoGuardrailAuthenticationError) as exc_info:
        client.evaluate(_context())
    assert exc_info.value.status_code == 401


def test_no_decision_is_ever_returned_on_any_failure_path():
    failing_transports = [
        lambda *a: (_ for _ in ()).throw(TimeoutError("t")),
        lambda *a: (_ for _ in ()).throw(OSError("o")),
        lambda *a: (500, b"{}"),
        lambda *a: (401, b"{}"),
        lambda *a: (200, b"not json"),
        lambda *a: (200, json.dumps({"data": {"guardrailsResult": {"Allowed": "not-a-bool"}}}).encode()),
    ]
    for transport in failing_transports:
        client = AktoGuardrailClient(_config(), transport=transport)
        with pytest.raises(Exception):
            client.evaluate(_context())


def test_config_requires_base_url():
    with pytest.raises(AktoGuardrailConfigError):
        AktoGuardrailConfig(base_url="")


def test_config_from_env_requires_url(monkeypatch):
    monkeypatch.delenv("AKTO_GUARDRAIL_URL", raising=False)
    with pytest.raises(AktoGuardrailConfigError):
        AktoGuardrailConfig.from_env()


def test_config_from_env_reads_all_fields(monkeypatch):
    monkeypatch.setenv("AKTO_GUARDRAIL_URL", "https://guardrail.example.invalid")
    monkeypatch.setenv("AKTO_GUARDRAIL_API_KEY", "fake-jwt")
    monkeypatch.setenv("AKTO_GUARDRAIL_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("AKTO_GUARDRAIL_ENVIRONMENT", "dev")
    monkeypatch.setenv("AKTO_GUARDRAIL_ACCOUNT_ID", "12345")
    config = AktoGuardrailConfig.from_env()
    assert config.base_url == "https://guardrail.example.invalid"
    assert config.api_key == "fake-jwt"
    assert config.timeout_seconds == 3.5
    assert config.environment == "dev"
    assert config.account_id == "12345"


def test_request_uses_confirmed_endpoint_and_method():
    seen = {}

    def _transport(method, url, headers, body, timeout_seconds):
        seen["method"] = method
        seen["url"] = url
        return 200, json.dumps(_guardrails_response(True)).encode("utf-8")

    client = AktoGuardrailClient(_config(), transport=_transport)
    client.evaluate(_context())
    assert seen["method"] == "GET"
    assert "/api/http-proxy" in seen["url"]
    assert "guardrails=true" in seen["url"]
    assert "ingest_data=true" in seen["url"]


def test_request_body_matches_real_schema_fields():
    seen = {}

    def _transport(method, url, headers, body, timeout_seconds):
        seen["headers"] = headers
        seen["body"] = json.loads(body)
        return 200, json.dumps(_guardrails_response(True)).encode("utf-8")

    client = AktoGuardrailClient(_config(), transport=_transport)
    ctx = _context()
    client.evaluate(ctx)

    body = seen["body"]
    assert body["path"] == f"/mcp/{ctx.mcp_target}/{ctx.bare_tool_name}"
    assert body["method"] == TOOL_CALL_METHOD_VALUE
    assert body["contextSource"] == CONTEXT_SOURCE
    assert body["source"] == SOURCE
    assert json.loads(body["tag"]) == {"source": "AGENTIC"}
    # Mandatory for the Guardrail Engine to record this traffic in the dashboard.
    assert body["statusCode"] == "200"
    assert body["status"] == "200"
    assert body["time"].isdigit()
    assert body["destIp"] == "127.0.0.1"
    assert body["type"] is None
    assert body["akto_vxlan_id"] == "0"
    assert body["is_pending"] == "false"
    assert body["responseHeaders"] == "{}"
    request_headers = json.loads(body["requestHeaders"])
    assert request_headers["host"] == UNKNOWN_AGENT_HOST  # no requesting_agent set on this context
    payload = json.loads(body["requestPayload"])
    assert payload["tool_name"] == ctx.tool_name
    assert payload["tool_arguments"] == ctx.tool_arguments


def test_host_uses_requesting_agent_when_available():
    seen = {}

    def _transport(method, url, headers, body, timeout_seconds):
        seen["body"] = json.loads(body)
        return 200, json.dumps(_guardrails_response(True)).encode("utf-8")

    client = AktoGuardrailClient(_config(), transport=_transport)
    ctx = _context(requesting_agent="arn:aws:iam::000000000000:role/my-agent")
    client.evaluate(ctx)
    request_headers = json.loads(seen["body"]["requestHeaders"])
    assert request_headers["host"] == "arn:aws:iam::000000000000:role/my-agent"


def test_host_never_uses_mcp_target_or_tool_name_as_fallback():
    """host identifies WHO is calling; mcp_target/tool_name identify WHAT is
    being called. Conflating them would mislabel traffic in the dashboard,
    so a missing agent identity must report as missing, not silently
    substitute the target or tool name."""
    seen = {}

    def _transport(method, url, headers, body, timeout_seconds):
        seen["body"] = json.loads(body)
        return 200, json.dumps(_guardrails_response(True)).encode("utf-8")

    client = AktoGuardrailClient(_config(), transport=_transport)
    ctx = _context(requesting_agent=None, mcp_target="mac-akto-api-mcp")
    client.evaluate(ctx)
    request_headers = json.loads(seen["body"]["requestHeaders"])
    assert request_headers["host"] == UNKNOWN_AGENT_HOST
    assert request_headers["host"] != ctx.mcp_target
    assert request_headers["host"] != ctx.tool_name


def test_explicit_account_id_overrides_url_derived_one():
    seen = {}

    def _transport(method, url, headers, body, timeout_seconds):
        seen["body"] = json.loads(body)
        return 200, json.dumps(_guardrails_response(True)).encode("utf-8")

    # _config()'s default base_url starts with "1234567890-" -- explicit
    # account_id should still win.
    client = AktoGuardrailClient(_config(account_id="98765"), transport=_transport)
    client.evaluate(_context())
    assert seen["body"]["akto_account_id"] == "98765"


def test_account_id_derived_from_guardrail_url_when_not_configured():
    seen = {}

    def _transport(method, url, headers, body, timeout_seconds):
        seen["body"] = json.loads(body)
        return 200, json.dumps(_guardrails_response(True)).encode("utf-8")

    client = AktoGuardrailClient(_config(base_url="https://1234567890-guardrails.akto.io"), transport=_transport)
    client.evaluate(_context())
    assert seen["body"]["akto_account_id"] == "1234567890"


def test_account_id_omitted_when_url_has_no_account_prefix():
    seen = {}

    def _transport(method, url, headers, body, timeout_seconds):
        seen["body"] = json.loads(body)
        return 200, json.dumps(_guardrails_response(True)).encode("utf-8")

    client = AktoGuardrailClient(_config(base_url="https://guardrails.example.invalid"), transport=_transport)
    client.evaluate(_context())
    assert "akto_account_id" not in seen["body"]


def test_correlation_header_and_session_in_request_headers():
    seen = {}

    def _transport(method, url, headers, body, timeout_seconds):
        seen["headers"] = headers
        seen["body"] = json.loads(body)
        return 200, json.dumps(_guardrails_response(True)).encode("utf-8")

    client = AktoGuardrailClient(_config(), transport=_transport)
    client.evaluate(_context(correlation_id="corr-xyz", session_id="sess-abc"))
    assert seen["headers"]["x-request-id"] == "corr-xyz"
    request_headers = json.loads(seen["body"]["requestHeaders"])
    assert request_headers["x-session-id"] == "sess-abc"


def test_api_key_sent_as_header_without_bearer_prefix():
    seen = {}

    def _transport(method, url, headers, body, timeout_seconds):
        seen["headers"] = headers
        seen["body"] = json.loads(body)
        return 200, json.dumps(_guardrails_response(True)).encode("utf-8")

    client = AktoGuardrailClient(_config(api_key="super-secret-jwt"), transport=_transport)
    client.evaluate(_context())
    assert seen["headers"]["Authorization"] == "super-secret-jwt"
    assert "super-secret-jwt" not in json.dumps(seen["body"])


def test_no_api_key_means_no_auth_header():
    seen = {}

    def _transport(method, url, headers, body, timeout_seconds):
        seen["headers"] = headers
        return 200, json.dumps(_guardrails_response(True)).encode("utf-8")

    client = AktoGuardrailClient(_config(api_key=None), transport=_transport)
    client.evaluate(_context())
    assert "Authorization" not in seen["headers"]
