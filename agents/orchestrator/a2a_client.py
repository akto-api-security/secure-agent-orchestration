"""A2A delegation to the Phase 2 delegated agents (API Security Agent /
Agentic Security Agent), both running on AgentCore Runtime.

Sends a standard A2A JSON-RPC `message/send` request via boto3's
`bedrock-agentcore` `invoke_agent_runtime` -- the same data-plane call
Phase 2's own README documents for testing those agents, and the same
mechanism the Terraform-created `asl-<agent>-invoke-<env>` IAM policies
exist to authorize. boto3 handles SigV4 signing itself; this module doesn't
need to hand-roll it the way `gateway_tool.py` does for the raw Gateway HTTP
endpoint in Phase 2.
"""

import json
import logging
import os
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

# Kept distinct from AWS_REGION, which the AgentCore Runtime platform
# reserves for its own use (same reasoning Phase 2's gateway_tool.py already
# documents for GATEWAY_REGION).
AGENT_REGION = os.environ.get("AGENT_REGION") or boto3.Session().region_name or "us-east-1"

# Generous but bounded: a delegated agent call involves a Bedrock model
# invocation plus a Gateway/MCP round trip, so a low timeout would false-
# positive on normal latency. No retry loop -- the brief asks for basic
# error handling, not retry infrastructure.
_CLIENT_CONFIG = Config(connect_timeout=10, read_timeout=60, retries={"max_attempts": 1})

_client = boto3.client("bedrock-agentcore", region_name=AGENT_REGION, config=_CLIENT_CONFIG)


class DelegatedAgentError(Exception):
    """Raised for any failure to get a usable answer from a delegated agent."""


def _build_a2a_request(question: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": question}],
                "messageId": str(uuid.uuid4()),
            }
        },
    }


def invoke_delegated_agent(runtime_arn: str, question: str, correlation_id: str) -> str:
    """Send `question` to the delegated agent at `runtime_arn` over A2A and
    return its answer text. Raises DelegatedAgentError on any failure
    (unavailable agent, timeout, or a malformed/error A2A response)."""
    payload = json.dumps(_build_a2a_request(question)).encode("utf-8")

    try:
        response = _client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            payload=payload,
            traceId=correlation_id,
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        raise DelegatedAgentError(f"A2A call failed ({error_code}): {exc}") from exc
    except BotoCoreError as exc:
        raise DelegatedAgentError(f"A2A call failed: {exc}") from exc

    status_code = response.get("statusCode")
    logger.info(
        "[%s] Delegated agent response: runtime=%s statusCode=%s",
        correlation_id,
        runtime_arn,
        status_code,
    )

    body = response["response"].read()
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise DelegatedAgentError(f"Delegated agent returned malformed JSON: {exc}") from exc

    if "error" in result:
        raise DelegatedAgentError(f"Delegated agent returned an A2A error: {result['error']}")

    try:
        parts = result["result"]["artifacts"][0]["parts"]
        text = "".join(part.get("text", "") for part in parts)
    except (KeyError, IndexError, TypeError) as exc:
        raise DelegatedAgentError(
            f"Delegated agent response missing expected A2A artifact/parts shape: {exc}"
        ) from exc

    if not text.strip():
        raise DelegatedAgentError("Delegated agent returned an empty answer")

    return text
