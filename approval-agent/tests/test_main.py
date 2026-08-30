"""End-to-end tests of main.py's action dispatch, wiring together the same
DynamoDB/KMS fakes used by test_state.py/test_grants.py. This is the
closest thing to a real run of the Approval Agent without touching AWS --
it exercises the full deterministic-approval and grant-replay chains this
phase's Definition of Done requires.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("APPROVAL_STATE_TABLE", "fake-table")
os.environ.setdefault("GRANT_KMS_KEY_ID", "arn:aws:kms:us-east-1:000000000000:key/fake-key")

import main  # noqa: E402
import semantic  # noqa: E402

from test_grants import _FakeKMS  # noqa: E402
from test_state import _FakeTable  # noqa: E402


def _wire_fakes(monkeypatch):
    monkeypatch.setattr("grants._kms", _FakeKMS())
    monkeypatch.setattr("state._table", _FakeTable())


def _authorize(**overrides):
    payload = {
        "action": "authorize",
        "correlation_id": "corr-1",
        "method": "tools/call",
        "tool_name": "mac-akto-api-mcp___sendFeedback",
        "bare_tool_name": "sendFeedback",
        "target": "mac-akto-api-mcp",
        "arguments": {"feedback": "great docs"},
        "grant": None,
        "requesting_principal": "arn:aws:sts::000000000000:assumed-role/test",
    }
    payload.update(overrides)
    return main.invoke(payload)


def test_send_feedback_requires_approval_with_no_llm_call(monkeypatch):
    _wire_fakes(monkeypatch)

    def _fail(*a, **k):
        raise AssertionError("sendFeedback must not invoke the LLM")

    monkeypatch.setattr(semantic, "evaluate", _fail)
    result = _authorize()
    assert result["decision"] == "APPROVAL_REQUIRED"
    assert result["llm_invoked"] is False
    assert result["approval_id"].startswith("appr-")


def test_normal_search_is_allowed(monkeypatch):
    _wire_fakes(monkeypatch)
    result = _authorize(
        tool_name="mac-akto-api-mcp___searchDocumentation",
        bare_tool_name="searchDocumentation",
        arguments={"query": "OWASP API Security Top 10"},
    )
    assert result["decision"] == "ALLOW"


def test_dast_query_requires_hitl_with_llm_invoked(monkeypatch):
    _wire_fakes(monkeypatch)
    monkeypatch.setattr(
        semantic, "_classify_dast", lambda request: (True, "asks to run a DAST scan")
    )
    result = _authorize(
        tool_name="mac-akto-api-mcp___searchDocumentation",
        bare_tool_name="searchDocumentation",
        arguments={"query": "Run a DAST scan against this API"},
    )
    assert result["decision"] == "HITL_REQUIRED"
    assert result["llm_invoked"] is True
    assert result["hitl_id"].startswith("hitl-")


def test_full_approve_then_grant_allows_exactly_once(monkeypatch):
    _wire_fakes(monkeypatch)
    pending = _authorize()
    approval_id = pending["approval_id"]

    decide = main.invoke({"action": "decide", "reference_id": approval_id, "decision": "approve", "approver": "alice"})
    assert decide["status"] == "ok"
    grant = decide["grant"]
    assert grant

    retried = _authorize(grant=grant)
    assert retried["decision"] == "ALLOW"
    assert retried["decision_mode"] == "grant_verification"

    # Replay: the exact same grant, same arguments, must now be rejected.
    replayed = _authorize(grant=grant)
    assert replayed["decision"] == "BLOCK"
    assert "replay" in replayed["reason"] or "already" in replayed["reason"].lower()


def test_deny_then_grant_is_never_issued(monkeypatch):
    _wire_fakes(monkeypatch)
    pending = _authorize()
    approval_id = pending["approval_id"]
    decide = main.invoke({"action": "decide", "reference_id": approval_id, "decision": "deny"})
    assert decide["status"] == "ok"
    assert decide["grant"] is None

    get_decision = main.invoke({"action": "get_decision", "reference_id": approval_id})
    assert get_decision["status"] == "DENIED"
    assert get_decision["grant"] is None


def test_changed_arguments_invalidate_the_grant(monkeypatch):
    _wire_fakes(monkeypatch)
    pending = _authorize(arguments={"feedback": "original text"})
    decide = main.invoke({"action": "decide", "reference_id": pending["approval_id"], "decision": "approve"})
    grant = decide["grant"]

    tampered = _authorize(grant=grant, arguments={"feedback": "a DIFFERENT message entirely"})
    assert tampered["decision"] == "BLOCK"


def test_approval_only_kind_rejects_additional_instruction(monkeypatch):
    _wire_fakes(monkeypatch)
    pending = _authorize()
    result = main.invoke({
        "action": "decide", "reference_id": pending["approval_id"], "decision": "instruction", "instruction_text": "only staging",
    })
    assert result["status"] == "error"


def test_hitl_additional_instruction_is_recorded_without_a_grant(monkeypatch):
    _wire_fakes(monkeypatch)
    monkeypatch.setattr(semantic, "_classify_dast", lambda request: (True, "DAST"))
    pending = _authorize(
        tool_name="mac-akto-api-mcp___searchDocumentation", bare_tool_name="searchDocumentation",
        arguments={"query": "Run a DAST scan"},
    )
    hitl_id = pending["hitl_id"]
    result = main.invoke({
        "action": "decide", "reference_id": hitl_id, "decision": "instruction", "instruction_text": "Only run this against staging.",
    })
    assert result["status"] == "ok"
    assert result["grant"] is None  # instruction is explicitly not a grant

    fetched = main.invoke({"action": "get_decision", "reference_id": hitl_id})
    assert fetched["instruction_text"] == "Only run this against staging."
    assert fetched["grant"] is None


def test_unknown_action_is_rejected():
    result = main.invoke({"action": "not_a_real_action"})
    assert result["status"] == "error"


def test_approval_agent_internal_error_fails_closed_not_allow(monkeypatch):
    _wire_fakes(monkeypatch)

    def _blow_up(request):
        raise RuntimeError("boom")

    import deterministic

    monkeypatch.setattr(deterministic, "evaluate", _blow_up)
    result = _authorize()
    assert result["decision"] == "BLOCK"
