"""Short-lived, cryptographically verifiable authorization grants.

A grant binds a human's APPROVE decision to one specific tool call: the
tool, its target, and a hash of its exact arguments. It is signed with an
asymmetric AWS KMS key (ECC_NIST_P256, Sign/Verify -- confirmed current KMS
API shape, not inferred) so the requesting agent -- which never has KMS
sign permission -- cannot forge one (see IAM: only this service's execution
role gets kms:Sign/kms:Verify on this key).

Grant format (a compact JSON string, so it fits in a single MCP tool-call
argument value):

    {"payload": "<base64url(payload_json_bytes)>",
     "signature": "<base64url(signature_bytes)>",
     "key_id": "<informational only -- verification always uses GRANT_KMS_KEY_ID>"}

Payload (what's actually signed):

    {"v": 1, "reference_id": "...", "correlation_id": "...", "tool_name": "...",
     "target": "...", "arguments_hash": "<sha256 hex>", "decision": "approve",
     "issued_at": <epoch seconds>, "expires_at": <epoch seconds>}

`correlation_id` is carried for audit/traceability only (it records the
*original* request's correlation_id, from when APPROVAL_REQUIRED was first
decided) -- it is NOT one of the binding checks on verification, because a
retried tools/call is a brand-new Gateway request and gets its own fresh
correlation_id at the interceptor (see interceptor/handler.py). Binding is
enforced via reference_id (tied to one DynamoDB record, consumable exactly
once) plus tool_name/target/arguments_hash (so the grant cannot authorize a
different tool, target, or a request whose arguments were changed after
approval).
"""

import base64
import hashlib
import json
import os
import time

import boto3
from botocore.exceptions import ClientError

GRANT_KMS_KEY_ID = os.environ["GRANT_KMS_KEY_ID"]
AWS_REGION = os.environ.get("AGENT_REGION") or boto3.Session().region_name or "us-east-1"
SIGNING_ALGORITHM = "ECDSA_SHA_256"

# Short-lived per the brief's explicit requirement ("the grant should be
# short-lived ... do not create permanent authorization").
GRANT_TTL_SECONDS = int(os.environ.get("GRANT_TTL_SECONDS", "300"))

_kms = boto3.client("kms", region_name=AWS_REGION)


class GrantError(Exception):
    """Any reason a grant is rejected: malformed, expired, mismatched, unverifiable."""


def arguments_hash(arguments: dict) -> str:
    """Deterministic hash of a tool call's arguments, used to bind a grant to
    the exact arguments approved -- changing any argument after approval
    invalidates the grant."""
    canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _b64u_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _b64u_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data.encode("ascii"))


def issue_grant(*, reference_id, correlation_id, tool_name, target, args_hash: str) -> str:
    """Sign and return a new grant for an APPROVED reference_id.

    Takes the already-computed arguments_hash (see arguments_hash() above)
    rather than the raw arguments dict, so the Approval Agent never needs to
    persist or re-handle the original tool-call arguments once a decision is
    recorded -- only their hash is stored in state.py's DynamoDB record.
    """
    now = int(time.time())
    payload = {
        "v": 1,
        "reference_id": reference_id,
        "correlation_id": correlation_id,
        "tool_name": tool_name,
        "target": target,
        "arguments_hash": args_hash,
        "decision": "approve",
        "issued_at": now,
        "expires_at": now + GRANT_TTL_SECONDS,
    }
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    response = _kms.sign(
        KeyId=GRANT_KMS_KEY_ID,
        Message=payload_bytes,
        MessageType="RAW",
        SigningAlgorithm=SIGNING_ALGORITHM,
    )

    envelope = {
        "payload": _b64u_encode(payload_bytes),
        "signature": _b64u_encode(response["Signature"]),
        "key_id": GRANT_KMS_KEY_ID,
    }
    return json.dumps(envelope, separators=(",", ":"))


def verify_grant(grant: str, *, tool_name, target, args_hash: str) -> dict:
    """Verify a grant against the tool call it's being redeemed for.

    Returns the grant's decoded payload dict on success.

    Raises GrantError -- with a specific, loggable reason -- for: malformed
    grant, bad signature (including one signed by a different/untrusted
    key, since verification always checks against our own configured
    GRANT_KMS_KEY_ID regardless of what the grant's own `key_id` field
    claims), expired grant, or a grant whose tool/target/arguments_hash
    doesn't match this exact request.

    Does NOT check reference_id status/consumption -- that is a stateful,
    atomic check the caller must do via state.mark_grant_consumed (KMS
    verification alone can't provide the single-use guarantee).
    """
    try:
        envelope = json.loads(grant)
        payload_bytes = _b64u_decode(envelope["payload"])
        signature_bytes = _b64u_decode(envelope["signature"])
        payload = json.loads(payload_bytes)
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        raise GrantError(f"malformed grant: {exc}") from exc

    try:
        result = _kms.verify(
            KeyId=GRANT_KMS_KEY_ID,
            Message=payload_bytes,
            MessageType="RAW",
            Signature=signature_bytes,
            SigningAlgorithm=SIGNING_ALGORITHM,
        )
    except ClientError as exc:
        raise GrantError(f"KMS verify failed: {exc}") from exc

    if not result.get("SignatureValid"):
        raise GrantError("invalid grant signature")

    if payload.get("expires_at", 0) < time.time():
        raise GrantError("expired grant")

    if payload.get("tool_name") != tool_name:
        raise GrantError("grant is for a different tool")
    if payload.get("target") != target:
        raise GrantError("grant is for a different target")
    if payload.get("arguments_hash") != args_hash:
        raise GrantError("grant arguments do not match this request (changed after approval)")

    return payload
