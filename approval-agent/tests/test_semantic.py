"""semantic.py calls a real Bedrock model in production. Unit tests mock the
bedrock-runtime client's converse() call -- they exist to verify the
request/response plumbing (tool-forced structured output parsing, decision
shape), not to make real model calls.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import semantic  # noqa: E402


def _fake_converse_response(is_dast_related, rationale="test rationale"):
    return {
        "output": {
            "message": {
                "content": [
                    {
                        "toolUse": {
                            "name": "classify_dast_relevance",
                            "input": {"is_dast_related": is_dast_related, "rationale": rationale},
                        }
                    }
                ]
            }
        }
    }


def test_dast_related_request_triggers_hitl(monkeypatch):
    monkeypatch.setattr(semantic._bedrock, "converse", lambda **kwargs: _fake_converse_response(True, "asks to run a DAST scan"))
    request = {
        "method": "tools/call",
        "tool_name": "mac-akto-api-mcp___searchDocumentation",
        "target": "mac-akto-api-mcp",
        "arguments": {"query": "Run a DAST scan against this API"},
    }
    decision = semantic.evaluate(request)
    assert decision is not None
    assert decision.decision == "HITL_REQUIRED"
    assert "DAST" in decision.reason


def test_unrelated_request_returns_none(monkeypatch):
    monkeypatch.setattr(semantic._bedrock, "converse", lambda **kwargs: _fake_converse_response(False, "general documentation question"))
    request = {
        "method": "tools/call",
        "tool_name": "mac-akto-api-mcp___searchDocumentation",
        "target": "mac-akto-api-mcp",
        "arguments": {"query": "What is OWASP API Security Top 10?"},
    }
    assert semantic.evaluate(request) is None


def test_converse_call_actually_forces_the_classifier_tool(monkeypatch):
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return _fake_converse_response(False)

    monkeypatch.setattr(semantic._bedrock, "converse", _capture)
    semantic.evaluate({"method": "tools/call", "tool_name": "x", "target": "y", "arguments": {}})
    assert captured["toolConfig"]["toolChoice"] == {"tool": {"name": "classify_dast_relevance"}}
