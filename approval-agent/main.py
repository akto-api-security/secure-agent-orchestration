"""Approval Agent -- AgentCore Runtime, HTTP protocol.

Owns all approval/HITL business logic. The interceptor Lambda
(interceptor/handler.py) is the only caller of the `authorize` action; a
human (via a small CLI, see scripts/) calls `decide`; whichever component
resumes a paused agent workflow calls `get_decision`.

Every branch below is logged with decision_mode/llm_invoked so it's always
possible to tell, after the fact, whether a given decision involved the LLM.
"""

import logging
import os
import uuid

from bedrock_agentcore.runtime import BedrockAgentCoreApp

import deterministic
import grants
import semantic
import state

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()


def _log(event, **fields):
    logger.info("%s %s", event, {k: v for k, v in fields.items() if v is not None})


def _handle_authorize(payload: dict) -> dict:
    correlation_id = payload.get("correlation_id")
    tool_name = payload.get("tool_name", "")
    bare_tool_name = payload.get("bare_tool_name", "")
    target = payload.get("target")
    arguments = payload.get("arguments") or {}
    grant = payload.get("grant")
    requesting_principal = payload.get("requesting_principal")
    args_hash = grants.arguments_hash(arguments)

    # A grant is present -- this is a retried/resumed request. Grant
    # verification is entirely deterministic (crypto + state lookups): no
    # LLM involved, regardless of whether the original decision was
    # deterministic or semantic.
    if grant:
        try:
            grant_payload = grants.verify_grant(grant, tool_name=tool_name, target=target, args_hash=args_hash)
        except grants.GrantError as exc:
            _log("grant_rejected", correlation_id=correlation_id, tool_name=tool_name, reason=str(exc))
            return {"decision": "BLOCK", "reason": f"grant rejected: {exc}", "decision_mode": "grant_verification", "llm_invoked": False}

        reference_id = grant_payload["reference_id"]
        try:
            record = state.get_record(reference_id)
        except state.RecordNotFoundError:
            _log("grant_rejected", correlation_id=correlation_id, reason="no matching approval record")
            return {"decision": "BLOCK", "reason": "grant references an unknown approval record", "decision_mode": "grant_verification", "llm_invoked": False}

        if record["status"] != "APPROVED":
            _log("grant_rejected", correlation_id=correlation_id, reference_id=reference_id, reason=f"record status={record['status']}")
            return {"decision": "BLOCK", "reason": f"approval record is {record['status']}, not APPROVED", "decision_mode": "grant_verification", "llm_invoked": False}

        if record.get("arguments_hash") != args_hash:
            # Defense in depth -- verify_grant already checked the grant's
            # own embedded arguments_hash; this additionally checks the
            # DynamoDB record wasn't itself somehow inconsistent with it.
            _log("grant_rejected", correlation_id=correlation_id, reference_id=reference_id, reason="record/grant arguments_hash mismatch")
            return {"decision": "BLOCK", "reason": "approval record does not match this request's arguments", "decision_mode": "grant_verification", "llm_invoked": False}

        try:
            state.mark_grant_consumed(reference_id)
        except state.GrantAlreadyConsumedError:
            _log("grant_replay_blocked", correlation_id=correlation_id, reference_id=reference_id)
            return {"decision": "BLOCK", "reason": "grant already used (replay)", "decision_mode": "grant_verification", "llm_invoked": False}

        _log("grant_allowed", correlation_id=correlation_id, reference_id=reference_id, tool_name=tool_name)
        return {"decision": "ALLOW", "reason": "valid grant", "decision_mode": "grant_verification", "llm_invoked": False}

    # No grant -- a fresh request. Deterministic rules first, no LLM call.
    request = {
        "method": payload.get("method"),
        "tool_name": tool_name,
        "bare_tool_name": bare_tool_name,
        "target": target,
        "arguments": arguments,
    }
    deterministic_decision = deterministic.evaluate(request)
    if deterministic_decision is not None:
        reference_id = f"appr-{uuid.uuid4()}"
        state.create_pending(
            reference_id,
            kind="approval",
            tool_name=tool_name,
            bare_tool_name=bare_tool_name,
            target=target,
            arguments_hash=args_hash,
            correlation_id=correlation_id,
            requesting_principal=requesting_principal,
            decision_mode="deterministic",
            human_question=deterministic_decision.human_question,
            reason=deterministic_decision.reason,
        )
        _log("approval_required", correlation_id=correlation_id, reference_id=reference_id, tool_name=tool_name, decision_mode="deterministic", llm_invoked=False)
        return {
            "decision": "APPROVAL_REQUIRED",
            "reason": deterministic_decision.reason,
            "decision_mode": "deterministic",
            "llm_invoked": False,
            "approval_id": reference_id,
            "human_question": deterministic_decision.human_question,
        }

    # No deterministic rule matched -- fall through to semantic (LLM) rules.
    semantic_decision = semantic.evaluate(request)
    if semantic_decision is not None:
        reference_id = f"hitl-{uuid.uuid4()}"
        state.create_pending(
            reference_id,
            kind="hitl",
            tool_name=tool_name,
            bare_tool_name=bare_tool_name,
            target=target,
            arguments_hash=args_hash,
            correlation_id=correlation_id,
            requesting_principal=requesting_principal,
            decision_mode="semantic",
            human_question=semantic_decision.human_question,
            reason=semantic_decision.reason,
        )
        _log("hitl_required", correlation_id=correlation_id, reference_id=reference_id, tool_name=tool_name, decision_mode="semantic", llm_invoked=True)
        return {
            "decision": "HITL_REQUIRED",
            "reason": semantic_decision.reason,
            "decision_mode": "semantic",
            "llm_invoked": True,
            "hitl_id": reference_id,
            "human_question": semantic_decision.human_question,
        }

    # Neither ruleset matched -- default allow. decision_mode reflects
    # whether a real LLM judgment call was actually part of reaching this
    # ALLOW: if any semantic rule exists, semantic.evaluate() above already
    # made a real model call and concluded "does not apply" -- that IS a
    # semantic judgment, not a deterministic outcome, so it's labeled
    # "semantic" here too (not just when a semantic rule matches). This
    # keeps decision_mode/llm_invoked always paired correctly (deterministic
    # + false, or semantic + true), never a mismatched deterministic + true.
    decision_mode = "semantic" if semantic.RULES else "deterministic"
    _log("allow_default", correlation_id=correlation_id, tool_name=tool_name, decision_mode=decision_mode, llm_invoked=bool(semantic.RULES))
    return {"decision": "ALLOW", "reason": "no approval/HITL rule matched", "decision_mode": decision_mode, "llm_invoked": bool(semantic.RULES)}


def _handle_decide(payload: dict) -> dict:
    reference_id = payload.get("reference_id")
    decision = payload.get("decision")
    instruction_text = payload.get("instruction_text")
    approver = payload.get("approver")

    if decision not in ("approve", "deny", "instruction"):
        return {"status": "error", "reason": f"decision must be approve/deny/instruction, got {decision!r}"}
    if not reference_id:
        return {"status": "error", "reason": "reference_id is required"}

    try:
        record = state.get_record(reference_id)
    except state.RecordNotFoundError:
        return {"status": "error", "reason": "no matching approval/HITL record"}

    if decision == "instruction" and record["kind"] != "hitl":
        return {"status": "error", "reason": "additional instructions are only valid for HITL requests, not deterministic approvals"}
    if instruction_text and decision != "instruction":
        return {"status": "error", "reason": "instruction_text is only valid when decision=instruction"}
    if decision == "instruction" and not instruction_text:
        return {"status": "error", "reason": "instruction_text is required when decision=instruction"}

    # The grant, when approving, is computed from the record fetched above
    # (still PENDING at this point) and written in the SAME conditional
    # transition below -- so the record never has status=APPROVED without
    # its grant already present.
    grant = None
    if decision == "approve":
        grant = grants.issue_grant(
            reference_id=reference_id,
            correlation_id=record["correlation_id"],
            tool_name=record["tool_name"],
            target=record["target"],
            args_hash=record["arguments_hash"],
        )

    try:
        state.record_decision(reference_id, decision=decision, approver=approver, instruction_text=instruction_text, grant=grant)
    except state.AlreadyDecidedError:
        return {"status": "error", "reason": f"{reference_id} was already decided (idempotent no-op, decision not changed)"}

    _log("decided", reference_id=reference_id, decision=decision, kind=record["kind"])
    return {"status": "ok", "reference_id": reference_id, "decision": decision, "kind": record["kind"], "grant": grant}


def _handle_get_decision(payload: dict) -> dict:
    reference_id = payload.get("reference_id")
    if not reference_id:
        return {"status": "error", "reason": "reference_id is required"}
    try:
        record = state.get_record(reference_id)
    except state.RecordNotFoundError:
        return {"status": "NOT_FOUND"}

    return {
        "status": record["status"],
        "kind": record["kind"],
        "decision": record.get("decision"),
        "grant": record.get("grant"),
        "instruction_text": record.get("instruction_text"),
        "tool_name": record.get("tool_name"),
        "target": record.get("target"),
        "correlation_id": record.get("correlation_id"),
        "human_question": record.get("human_question"),
    }


_ACTIONS = {
    "authorize": _handle_authorize,
    "decide": _handle_decide,
    "get_decision": _handle_get_decision,
}


@app.entrypoint
def invoke(payload: dict) -> dict:
    action = (payload or {}).get("action")
    handler = _ACTIONS.get(action)
    if handler is None:
        return {"status": "error", "reason": f"unknown or missing action: {action!r}, expected one of {list(_ACTIONS)}"}
    try:
        return handler(payload)
    except Exception:  # noqa: BLE001 -- fail closed: never let an unexpected error look like ALLOW
        logger.exception("approval agent internal error, failing closed")
        if action == "authorize":
            return {"decision": "BLOCK", "reason": "approval agent internal error (fail-closed)", "decision_mode": "error", "llm_invoked": False}
        return {"status": "error", "reason": "internal error"}


if __name__ == "__main__":
    logger.info("Approval Agent starting: table=%s, kms_key=%s", os.environ.get("APPROVAL_STATE_TABLE"), os.environ.get("GRANT_KMS_KEY_ID"))
    app.run()
