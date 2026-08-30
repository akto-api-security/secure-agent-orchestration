"""AgentCore Gateway REQUEST interceptor Lambda.

Phase 4 gave this handler one job: normalize the Gateway's MCP-target
interceptor event and evaluate it against the OPA policy bundled in
policies/main.rego (invoked as a subprocess -- see README.md "Why OPA as a
subprocess, not a library"). Phase 5 keeps that OPA pass as a first,
independent baseline layer (still fail-closed, still default-allow), but
routes every allowed tools/call on to the Approval Agent (a separate
AgentCore Runtime service -- approval-agent/) for the actual authorization
decision: ALLOW, BLOCK, APPROVAL_REQUIRED, or HITL_REQUIRED. This handler
does NOT itself decide which tools need approval or HITL -- that business
logic lives entirely in the Approval Agent (see
docs/phase-context/phase-5-context.md, "Locked responsibility model"). This
handler only routes to it and enforces whatever it decides.

Fail-closed: any error (malformed event, OPA eval failure, Approval Agent
invoke/response failure, unexpected exception) results in a BLOCK response,
never a silent ALLOW.
"""

import json
import logging
import os
import subprocess
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_HERE = os.path.dirname(os.path.abspath(__file__))
OPA_BIN_PATH = os.environ.get("OPA_BIN_PATH", os.path.join(_HERE, "bin", "opa"))
POLICY_PATH = os.environ.get("OPA_POLICY_PATH", os.path.join(_HERE, "policies", "main.rego"))
OPA_QUERY = "data.gateway.authz"
OPA_TIMEOUT_SECONDS = 5

# Phase 5: the Approval Agent (AgentCore Runtime, HTTP protocol -- same
# protocol/invocation mechanism already confirmed working for the Phase 3
# Orchestrator, not a new/unverified AWS capability). Required: there is no
# sensible fallback if this isn't wired.
APPROVAL_AGENT_RUNTIME_ARN = os.environ["APPROVAL_AGENT_RUNTIME_ARN"]
AGENT_REGION = os.environ.get("AGENT_REGION") or boto3.Session().region_name or "us-east-1"
APPROVAL_AGENT_TIMEOUT_SECONDS = int(os.environ.get("APPROVAL_AGENT_TIMEOUT_SECONDS", "20"))

# Reserved argument key used to carry a signed grant on a retried tools/call.
# Never forwarded to the real MCP target -- stripped from `arguments` before
# any transformedGatewayRequest is returned (see _handle_tool_call below).
GRANT_ARG_KEY = "_asl_grant"

INTERCEPTOR_OUTPUT_VERSION = "1.0"

_agentcore_client = boto3.client(
    "bedrock-agentcore",
    region_name=AGENT_REGION,
    config=Config(connect_timeout=5, read_timeout=APPROVAL_AGENT_TIMEOUT_SECONDS, retries={"max_attempts": 1}),
)


class PolicyEvaluationError(Exception):
    """Raised when OPA itself fails to produce a decision (not a policy deny)."""


class ApprovalAgentError(Exception):
    """Raised when the Approval Agent can't be reached or returns something unusable."""


def _extract_target_and_tool(namespaced_tool_name):
    """Gateway namespaces tool names as '<target>___<tool>' (see Phase 1)."""
    if namespaced_tool_name and "___" in namespaced_tool_name:
        target, _, tool = namespaced_tool_name.partition("___")
        return target, tool
    return None, namespaced_tool_name


def _build_opa_input(rpc_body):
    method = rpc_body.get("method")
    params = rpc_body.get("params") or {}
    tool_name = params.get("name", "")
    target, bare_tool_name = _extract_target_and_tool(tool_name)
    return {
        "method": method,
        "tool_name": tool_name,
        "bare_tool_name": bare_tool_name,
        "target": target,
    }


def _evaluate_opa(opa_input):
    try:
        proc = subprocess.run(
            [
                OPA_BIN_PATH,
                "eval",
                "--format",
                "json",
                "--data",
                POLICY_PATH,
                "--stdin-input",
                OPA_QUERY,
            ],
            input=json.dumps(opa_input).encode("utf-8"),
            capture_output=True,
            timeout=OPA_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PolicyEvaluationError(f"failed to invoke OPA binary: {exc}") from exc

    if proc.returncode != 0:
        raise PolicyEvaluationError(
            f"opa eval exited {proc.returncode}: {proc.stderr.decode('utf-8', 'replace')}"
        )

    try:
        result = json.loads(proc.stdout)
        return result["result"][0]["expressions"][0]["value"]
    except (KeyError, IndexError, ValueError) as exc:
        raise PolicyEvaluationError(f"unexpected opa eval output: {proc.stdout!r}") from exc


def _call_approval_agent(payload):
    """Invoke the Approval Agent's AgentCore Runtime (HTTP protocol) and return
    its decoded JSON response. Raises ApprovalAgentError on any failure --
    the caller treats that as fail-closed (BLOCK), never a silent ALLOW.
    """
    try:
        response = _agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=APPROVAL_AGENT_RUNTIME_ARN,
            payload=json.dumps(payload).encode("utf-8"),
            traceId=payload.get("correlation_id"),
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        raise ApprovalAgentError(f"approval agent invoke failed ({error_code}): {exc}") from exc
    except BotoCoreError as exc:
        raise ApprovalAgentError(f"approval agent invoke failed: {exc}") from exc

    body = response["response"].read()
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ApprovalAgentError(f"approval agent returned malformed JSON: {exc}") from exc

    if not isinstance(result, dict) or "decision" not in result:
        raise ApprovalAgentError(f"approval agent response missing 'decision': {result!r}")

    return result


def _allow_response(rpc_body):
    return {
        "interceptorOutputVersion": INTERCEPTOR_OUTPUT_VERSION,
        "mcp": {"transformedGatewayRequest": {"body": rpc_body}},
    }


def _deny_response(request_id, reason, correlation_id, error_code=-32001):
    return {
        "interceptorOutputVersion": INTERCEPTOR_OUTPUT_VERSION,
        "mcp": {
            "transformedGatewayResponse": {
                "statusCode": 200,
                "body": {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": error_code,
                        "message": "Blocked by gateway policy",
                        "data": {"reason": reason, "correlation_id": correlation_id},
                    },
                },
            }
        },
    }


# Phase 5: two new terminal-but-not-BLOCK outcomes. Neither AWS's interceptor
# docs nor any existing convention in this project define codes for these --
# same situation Phase 4 was already in for BLOCK (-32001)/fail-closed
# (-32000), so this project picks its own, documented here and in
# interceptor/README.md.
_DECISION_CODES = {"APPROVAL_REQUIRED": -32010, "HITL_REQUIRED": -32011}


def _pending_response(request_id, decision, correlation_id, approval_result):
    data = {
        "decision": decision,
        "reason": approval_result.get("reason", ""),
        "correlation_id": correlation_id,
        "reference_id": approval_result.get("approval_id") or approval_result.get("hitl_id"),
        "human_question": approval_result.get("human_question", ""),
    }
    return {
        "interceptorOutputVersion": INTERCEPTOR_OUTPUT_VERSION,
        "mcp": {
            "transformedGatewayResponse": {
                "statusCode": 200,
                "body": {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": _DECISION_CODES[decision], "message": decision, "data": data},
                },
            }
        },
    }


def _log(correlation_id, tool_name, target, decision, policy_name, extra=None):
    record = {
        "correlation_id": correlation_id,
        "tool_name": tool_name,
        "target": target,
        "policy_decision": decision,
        "policy_name": policy_name,
    }
    if extra:
        record.update(extra)
    logger.info(json.dumps(record))


def _handle_tool_call(rpc_body, request_id, correlation_id, opa_input, requesting_principal):
    """OPA already allowed this request -- ask the Approval Agent for the
    definitive decision on this specific tool call (fresh, or a retry
    carrying a grant) and enforce it.
    """
    params = rpc_body.get("params") or {}
    arguments = dict(params.get("arguments") or {})
    # Never forwarded to the real MCP target -- see GRANT_ARG_KEY.
    grant = arguments.pop(GRANT_ARG_KEY, None)

    approval_payload = {
        "action": "authorize",
        "correlation_id": correlation_id,
        "method": opa_input["method"],
        "tool_name": opa_input["tool_name"],
        "bare_tool_name": opa_input["bare_tool_name"],
        "target": opa_input["target"],
        "arguments": arguments,
        "grant": grant,
        "requesting_principal": requesting_principal,
    }

    approval_result = _call_approval_agent(approval_payload)
    decision = approval_result.get("decision")
    reason = approval_result.get("reason", "")

    _log(
        correlation_id,
        opa_input["tool_name"],
        opa_input["target"],
        decision,
        "approval_agent",
        extra={
            "method": opa_input["method"],
            "decision_mode": approval_result.get("decision_mode"),
            "llm_invoked": approval_result.get("llm_invoked", False),
        },
    )

    if decision == "ALLOW":
        clean_body = dict(rpc_body)
        if grant is not None:
            clean_params = dict(params)
            clean_params["arguments"] = arguments
            clean_body["params"] = clean_params
        return _allow_response(clean_body)
    if decision == "BLOCK":
        return _deny_response(request_id, reason or "blocked by approval agent", correlation_id)
    if decision in _DECISION_CODES:
        return _pending_response(request_id, decision, correlation_id, approval_result)

    raise ApprovalAgentError(f"unrecognized decision from approval agent: {decision!r}")


def handler(event, context):
    correlation_id = str(uuid.uuid4())
    request_id = None

    # Logged before any parsing, at DEBUG, so the very first live
    # invocation is empirical evidence of the actual event shape this
    # account's Gateway sends. Safe to log in full: passRequestHeaders is
    # false (see Terraform module), so no headers/bearer-token/SigV4
    # material is ever present in this payload. A retried request's grant
    # lives in `arguments`, not headers, and is opaque ciphertext/signature
    # material, not a secret whose plaintext would be sensitive to log.
    logger.debug(json.dumps({"correlation_id": correlation_id, "raw_event": event}))

    try:
        mcp = event.get("mcp")
        if mcp is None:
            raise ValueError("event has no 'mcp' key -- not an MCP-target interceptor event")

        gateway_request = mcp.get("gatewayRequest") or {}
        rpc_body = gateway_request.get("body") or {}
        request_id = rpc_body.get("id")

        if not rpc_body.get("method"):
            raise ValueError("request body missing 'method' -- cannot evaluate policy")

        opa_input = _build_opa_input(rpc_body)
        opa_decision = _evaluate_opa(opa_input)
        opa_allow = bool(opa_decision.get("allow", False))

        if not opa_allow:
            reason = opa_decision.get("block_reason") or "blocked by policy"
            _log(
                correlation_id,
                opa_input["tool_name"],
                opa_input["target"],
                "block",
                "gateway.authz",
                extra={"method": opa_input["method"], "decision_mode": "opa"},
            )
            return _deny_response(request_id, reason, correlation_id)

        if opa_input["method"] != "tools/call":
            # tools/list, initialize, etc. -- nothing to authorize per-tool;
            # the Approval Agent exists to gate tool execution, not catalog
            # browsing, so it isn't consulted for these.
            _log(correlation_id, opa_input["tool_name"], opa_input["target"], "allow", "gateway.authz",
                 extra={"method": opa_input["method"], "decision_mode": "opa"})
            return _allow_response(rpc_body)

        # Best-effort only: observed present on a real invocation (Phase 4),
        # not documented by AWS -- see docs/phase-context/phase-4-context.md
        # "Known limitations". Absent entirely if unavailable.
        requesting_principal = ((gateway_request.get("context") or {}).get("identity") or {}).get("awsPrincipalArn")

        return _handle_tool_call(rpc_body, request_id, correlation_id, opa_input, requesting_principal)

    except Exception as exc:  # noqa: BLE001 -- fail-closed on any unexpected error
        logger.exception("interceptor error, failing closed")
        _log(
            correlation_id,
            None,
            None,
            "block",
            "fail-closed",
            extra={"error": str(exc)},
        )
        return _deny_response(
            request_id,
            "interceptor internal error (fail-closed)",
            correlation_id,
            error_code=-32000,
        )
