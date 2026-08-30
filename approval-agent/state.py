"""DynamoDB-backed state for pending/decided approval and HITL requests.

One table, one item per request, keyed by `reference_id` (the interceptor's
approval_id/hitl_id). All state transitions here are conditional writes --
this is the idempotency/replay-prevention boundary this design
requires ("a request must not execute multiple times because of retries,
duplicate human responses, ..."; "grant being reused ... is not possible").

DynamoDB's own `expires_at` TTL attribute is set for hygiene (automatic
cleanup of old items) but is NOT the security control for expiry -- TTL
deletion is documented by AWS as best-effort and can lag by hours. The
authoritative expiry check is the application-level comparison against
`time.time()` done here and in grants.py.
"""

import os
import time

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = os.environ["APPROVAL_STATE_TABLE"]
AWS_REGION = os.environ.get("AGENT_REGION") or boto3.Session().region_name or "us-east-1"

# How long a PENDING request stays open for a human to decide (application-
# level check; also used to set the DynamoDB TTL attribute for cleanup).
PENDING_TTL_SECONDS = int(os.environ.get("APPROVAL_PENDING_TTL_SECONDS", "900"))

_table = boto3.resource("dynamodb", region_name=AWS_REGION).Table(TABLE_NAME)


class RecordExistsError(Exception):
    """Raised when a reference_id collides with an existing item."""


class RecordNotFoundError(Exception):
    """Raised when a reference_id has no item."""


class AlreadyDecidedError(Exception):
    """Raised when a decision is attempted on a request that isn't PENDING."""


class GrantAlreadyConsumedError(Exception):
    """Raised when a grant is redeemed a second time (replay)."""


def create_pending(reference_id, *, kind, tool_name, bare_tool_name, target, arguments_hash,
                    correlation_id, requesting_principal, decision_mode, human_question, reason):
    now = int(time.time())
    item = {
        "reference_id": reference_id,
        "kind": kind,  # "approval" | "hitl"
        "status": "PENDING",
        "tool_name": tool_name,
        "bare_tool_name": bare_tool_name,
        "target": target,
        "arguments_hash": arguments_hash,
        "correlation_id": correlation_id,
        "requesting_principal": requesting_principal or "",
        "decision_mode": decision_mode,  # "deterministic" | "semantic"
        "human_question": human_question,
        "reason": reason,
        "created_at": now,
        "expires_at": now + PENDING_TTL_SECONDS,
    }
    try:
        _table.put_item(Item=item, ConditionExpression="attribute_not_exists(reference_id)")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise RecordExistsError(reference_id) from exc
        raise
    return item


def get_record(reference_id):
    response = _table.get_item(Key={"reference_id": reference_id})
    item = response.get("Item")
    if item is None:
        raise RecordNotFoundError(reference_id)
    return item


def record_decision(reference_id, *, decision, approver=None, instruction_text=None, grant=None):
    """Transition a PENDING record to its human decision. Conditional on the
    current status still being PENDING -- a second decision attempt (a
    duplicate human response, a retried A2A/network call) raises
    AlreadyDecidedError instead of silently overwriting the first decision.
    """
    now = int(time.time())
    status = {"approve": "APPROVED", "deny": "DENIED", "instruction": "INSTRUCTED"}[decision]

    # Every non-key attribute name is aliased (#name) -- not just the ones
    # known offhand to collide with DynamoDB's reserved-word list (e.g.
    # "grant" is one); aliasing all of them defensively avoids re-guessing
    # which other plain-English names might collide.
    update_expr = "SET #status = :status, #decision = :decision, #decided_at = :decided_at"
    expr_values = {":status": status, ":decision": decision, ":decided_at": now, ":pending": "PENDING"}
    expr_names = {"#status": "status", "#decision": "decision", "#decided_at": "decided_at"}

    if approver:
        update_expr += ", #approver = :approver"
        expr_values[":approver"] = approver
        expr_names["#approver"] = "approver"
    if instruction_text:
        update_expr += ", #instruction_text = :instruction_text"
        expr_values[":instruction_text"] = instruction_text
        expr_names["#instruction_text"] = "instruction_text"
    if grant:
        update_expr += ", #grant = :grant"
        expr_values[":grant"] = grant
        expr_names["#grant"] = "grant"

    try:
        _table.update_item(
            Key={"reference_id": reference_id},
            UpdateExpression=update_expr,
            ConditionExpression="attribute_exists(reference_id) AND #status = :pending",
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise AlreadyDecidedError(reference_id) from exc
        raise


def mark_grant_consumed(reference_id):
    """Atomically mark a grant as redeemed. Fails if already consumed --
    this is what makes grant replay impossible: the second verification
    attempt for the same reference_id always loses this race.
    """
    try:
        _table.update_item(
            Key={"reference_id": reference_id},
            UpdateExpression="SET #grant_consumed_at = :now",
            ConditionExpression="attribute_not_exists(#grant_consumed_at)",
            ExpressionAttributeNames={"#grant_consumed_at": "grant_consumed_at"},
            ExpressionAttributeValues={":now": int(time.time())},
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise GrantAlreadyConsumedError(reference_id) from exc
        raise
