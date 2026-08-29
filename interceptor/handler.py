"""AgentCore Gateway REQUEST interceptor Lambda.

Normalizes the Gateway's MCP-target interceptor event, evaluates it against
the OPA policy bundled in policies/main.rego (invoked as a subprocess -- see
README.md "Why OPA as a subprocess, not a library"), and returns either an
unmodified passthrough (ALLOW) or a short-circuiting JSON-RPC error response
(BLOCK), per the interceptor output contract documented at
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-interceptors-types.html

Fail-closed: any error (malformed event, OPA eval failure, unexpected
exception) results in a BLOCK response, not a silent ALLOW.
"""

import json
import logging
import os
import subprocess
import uuid

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_HERE = os.path.dirname(os.path.abspath(__file__))
OPA_BIN_PATH = os.environ.get("OPA_BIN_PATH", os.path.join(_HERE, "bin", "opa"))
POLICY_PATH = os.environ.get("OPA_POLICY_PATH", os.path.join(_HERE, "policies", "main.rego"))
OPA_QUERY = "data.gateway.authz"
OPA_TIMEOUT_SECONDS = 5

INTERCEPTOR_OUTPUT_VERSION = "1.0"


class PolicyEvaluationError(Exception):
    """Raised when OPA itself fails to produce a decision (not a policy deny)."""


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
        "arguments": params.get("arguments", {}),
    }


def _evaluate_policy(opa_input):
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


def handler(event, context):
    correlation_id = str(uuid.uuid4())
    request_id = None

    # Logged before any parsing, at DEBUG, so the very first live
    # invocation is empirical evidence of the actual event shape this
    # account's Gateway sends -- not just trust in AWS's documented schema.
    # Safe to log in full: passRequestHeaders is false (see Terraform
    # module), so no headers/bearer-token/SigV4 material is ever present
    # in this payload. Set LOG_LEVEL=DEBUG for the first real test, then
    # drop back to INFO -- this isn't meant to run at DEBUG permanently.
    logger.debug(json.dumps({"correlation_id": correlation_id, "raw_event": event}))

    try:
        mcp = event.get("mcp")
        if mcp is None:
            raise ValueError("event has no 'mcp' key -- not an MCP-target interceptor event")

        rpc_body = (mcp.get("gatewayRequest") or {}).get("body") or {}
        request_id = rpc_body.get("id")

        if not rpc_body.get("method"):
            raise ValueError("request body missing 'method' -- cannot evaluate policy")

        opa_input = _build_opa_input(rpc_body)
        decision = _evaluate_policy(opa_input)
        allow = bool(decision.get("allow", False))
        reason = decision.get("block_reason", "")

        _log(
            correlation_id,
            opa_input["tool_name"],
            opa_input["target"],
            "allow" if allow else "block",
            "gateway.authz",
            extra={"method": opa_input["method"]},
        )

        if allow:
            return _allow_response(rpc_body)
        return _deny_response(request_id, reason or "blocked by policy", correlation_id)

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
