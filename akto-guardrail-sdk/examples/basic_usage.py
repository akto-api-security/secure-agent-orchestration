#!/usr/bin/env python3
"""Runnable example of the Akto Guardrail SDK's public interface.

Uses a scripted fake transport, so this runs with no network access and no
real credentials. To call a real Guardrail Engine instead, drop the
`transport` argument and use `AktoGuardrailConfig.from_env()`:

    config = AktoGuardrailConfig.from_env()
    client = AktoGuardrailClient(config)

Run it directly:

    cd akto-guardrail-sdk
    python3 examples/basic_usage.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from akto_guardrail_sdk import (  # noqa: E402
    AktoGuardrailClient,
    AktoGuardrailConfig,
    AktoGuardrailError,
    Decision,
    RequestContext,
)


def fake_transport(allowed):
    def _transport(method, url, headers, body, timeout_seconds):
        payload = {"data": {"guardrailsResult": {"Allowed": allowed, "Reason": f"example: allowed={allowed}"}}}
        return 200, json.dumps(payload).encode()

    return _transport


def handle_decision(request_context, transport):
    config = AktoGuardrailConfig(base_url="https://guardrail.akto.example", api_key="example-key")
    client = AktoGuardrailClient(config, transport=transport)

    try:
        decision = client.evaluate(request_context)
    except AktoGuardrailError as exc:
        print(f"  -> SDK error ({type(exc).__name__}): {exc} -- treat as BLOCK")
        return

    print(f"  -> decision={decision.decision.value} reason={decision.reason!r} latency_ms={decision.latency_ms:.2f}")

    if decision.decision == Decision.ALLOW:
        print("     (caller would proceed with its own existing enforcement/execution)")
    elif decision.decision == Decision.BLOCK:
        print("     (caller would deny, using its own existing deny/error path)")


def main():
    request_context = RequestContext(
        correlation_id="example-correlation-id",
        tool_name="mac-akto-api-mcp___searchDocumentation",
        bare_tool_name="searchDocumentation",
        mcp_target="mac-akto-api-mcp",
        tool_arguments={"query": "OWASP API security"},
        requesting_agent="arn:aws:iam::000000000000:role/example-agent-role",
    )

    print("ALLOW scenario:")
    handle_decision(request_context, fake_transport(allowed=True))

    print("\nBLOCK scenario:")
    handle_decision(request_context, fake_transport(allowed=False))

    print("\nSDK error scenario (simulated timeout):")

    def timeout_transport(method, url, headers, body, timeout_seconds):
        raise TimeoutError("simulated timeout")

    handle_decision(request_context, timeout_transport)


if __name__ == "__main__":
    main()
