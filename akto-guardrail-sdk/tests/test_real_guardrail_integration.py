"""Real Guardrail Engine integration test — not a unit test.

Unlike test_client.py, this makes an actual HTTPS call to a real Guardrail
Engine deployment. Skipped by default. To run it:

    cd akto-guardrail-sdk
    AKTO_GUARDRAIL_REAL_INTEGRATION_TEST=1 \\
    AKTO_GUARDRAIL_URL=https://<deployment> \\
    AKTO_GUARDRAIL_API_KEY=<credential, if that deployment requires one> \\
    python3 -m pytest tests/test_real_guardrail_integration.py -v

Do not point this at a production deployment — use a test/staging one.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from akto_guardrail_sdk import AktoGuardrailClient, AktoGuardrailConfig, Decision, RequestContext  # noqa: E402

_ENABLED = os.environ.get("AKTO_GUARDRAIL_REAL_INTEGRATION_TEST") == "1"

pytestmark = pytest.mark.skipif(
    not _ENABLED,
    reason="Requires AKTO_GUARDRAIL_REAL_INTEGRATION_TEST=1 plus a real AKTO_GUARDRAIL_URL.",
)


def test_real_allow_or_block_for_a_benign_request():
    config = AktoGuardrailConfig.from_env()
    client = AktoGuardrailClient(config)

    result = client.evaluate(
        RequestContext(
            correlation_id="real-integration-test-1",
            tool_name="example___benignTool",
            bare_tool_name="benignTool",
            mcp_target="example",
            tool_arguments={"query": "hello"},
        )
    )

    assert result.decision in (Decision.ALLOW, Decision.BLOCK)
    assert result.status_code == 200
