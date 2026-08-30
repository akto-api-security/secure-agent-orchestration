import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import deterministic  # noqa: E402


def test_send_feedback_requires_approval():
    request = {
        "method": "tools/call",
        "tool_name": "mac-akto-api-mcp___sendFeedback",
        "bare_tool_name": "sendFeedback",
        "target": "mac-akto-api-mcp",
        "arguments": {"feedback": "great docs"},
    }
    decision = deterministic.evaluate(request)
    assert decision is not None
    assert decision.decision == "APPROVAL_REQUIRED"
    assert "no LLM" in decision.reason


def test_search_documentation_has_no_deterministic_rule():
    request = {
        "method": "tools/call",
        "tool_name": "mac-akto-api-mcp___searchDocumentation",
        "bare_tool_name": "searchDocumentation",
        "target": "mac-akto-api-mcp",
        "arguments": {"query": "OWASP API security"},
    }
    assert deterministic.evaluate(request) is None
