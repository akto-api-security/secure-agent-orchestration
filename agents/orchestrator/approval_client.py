"""Orchestrator's read-only view into the Approval Agent's decision state.

Only ever calls the `get_decision` action -- the orchestrator (and, by
extension, whoever is invoking it) can check what a human decided, but has
no path here to `decide` on a human's behalf or read/construct a grant
directly. That capability is deliberately not exposed by this module (see
docs/phase-context/phase-5-context.md, "IAM" -- the orchestrator's execution
role only grants InvokeAgentRuntime on the Approval Agent's runtime, and
Terraform doesn't distinguish `get_decision` from `decide` at the IAM layer,
but this module's own code never sends anything but get_decision).
"""

import json
import logging
import os

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

APPROVAL_AGENT_RUNTIME_ARN = os.environ["APPROVAL_AGENT_RUNTIME_ARN"]
AGENT_REGION = os.environ.get("AGENT_REGION") or boto3.Session().region_name or "us-east-1"

_client = boto3.client(
    "bedrock-agentcore",
    region_name=AGENT_REGION,
    config=Config(connect_timeout=10, read_timeout=20, retries={"max_attempts": 1}),
)


class ApprovalAgentError(Exception):
    """Raised for any failure to read decision state from the Approval Agent."""


def get_decision(reference_id: str, correlation_id: str) -> dict:
    payload = json.dumps({"action": "get_decision", "reference_id": reference_id}).encode("utf-8")
    try:
        response = _client.invoke_agent_runtime(
            agentRuntimeArn=APPROVAL_AGENT_RUNTIME_ARN,
            payload=payload,
            traceId=correlation_id,
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        raise ApprovalAgentError(f"get_decision failed ({error_code}): {exc}") from exc
    except BotoCoreError as exc:
        raise ApprovalAgentError(f"get_decision failed: {exc}") from exc

    body = response["response"].read()
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ApprovalAgentError(f"get_decision returned malformed JSON: {exc}") from exc

    if "status" not in result:
        raise ApprovalAgentError(f"get_decision response missing 'status': {result!r}")

    return result
