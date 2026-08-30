import logging
import os
import uuid

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from a2a_client import DelegatedAgentError, DelegatedAgentResult, invoke_delegated_agent, resume_delegated_agent
from approval_client import ApprovalAgentError, get_decision
from router import Domain, classify

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

# Fail fast at startup if Terraform didn't wire these -- there's no sensible
# fallback runtime to delegate to.
AGENT_RUNTIME_ARNS = {
    Domain.API_SECURITY: os.environ["API_SECURITY_AGENT_RUNTIME_ARN"],
    Domain.AGENTIC_SECURITY: os.environ["AGENTIC_SECURITY_AGENT_RUNTIME_ARN"],
}

CLARIFICATION_MESSAGE = (
    "I can route this to either the API Security Agent (API security, DAST, "
    "API vulnerabilities/testing) or the Agentic Security Agent (Atlas, "
    "Argus, agentic/MCP/A2A/agent/AI security). Could you clarify which "
    "domain your question is about?"
)

_DECISION_TO_ACTION = {"APPROVED": "approve", "DENIED": "deny", "INSTRUCTED": "instruction"}


def _pending_response(correlation_id: str, domain: str, result: DelegatedAgentResult) -> dict:
    """Shape a paused (input_required) DelegatedAgentResult into an
    orchestrator response, carrying everything a later resume call needs in
    `resume_token` -- the orchestrator persists none of this itself (see
    a2a_client.py's own docstring on why runtime_session_id provides the
    affinity a resume needs)."""
    interrupt = result.interrupts[0]
    marker = interrupt.get("reason")
    marker = marker if isinstance(marker, dict) else {}
    reference_id = marker.get("reference_id")
    decision_kind = marker.get("asl_decision")
    human_question = marker.get("human_question") or result.text or "Human input is required before this can proceed."

    status = "approval_required" if decision_kind == "APPROVAL_REQUIRED" else "hitl_required"

    resume_token = {
        "runtime_arn": AGENT_RUNTIME_ARNS[Domain(domain)],
        "domain": domain,
        "context_id": result.context_id,
        "runtime_session_id": result.runtime_session_id,
        "task_id": result.task_id,
        "interrupt_id": interrupt.get("interruptId"),
        "reference_id": reference_id,
    }

    logger.info(
        "[%s] Delegation to %s paused: %s reference_id=%s",
        correlation_id, domain, status, reference_id,
    )
    return {
        "status": status,
        "correlation_id": correlation_id,
        "domain": domain,
        "response": human_question,
        "resume_token": resume_token,
    }


def _handle_fresh_request(question: str, correlation_id: str) -> dict:
    question = question.strip()
    route = classify(question)
    logger.info(
        "[%s] Received question, classified as %s (matched=%s)",
        correlation_id, route.domain.value if route.domain else "ambiguous", route.matched_keywords,
    )

    if route.domain is None:
        return {"status": "clarification_needed", "correlation_id": correlation_id, "response": CLARIFICATION_MESSAGE}

    runtime_arn = AGENT_RUNTIME_ARNS[route.domain]
    logger.info("[%s] Delegating to %s (%s)", correlation_id, route.domain.value, runtime_arn)

    try:
        result = invoke_delegated_agent(runtime_arn=runtime_arn, question=question, correlation_id=correlation_id)
    except DelegatedAgentError as exc:
        logger.error("[%s] Delegation to %s failed: %s", correlation_id, route.domain.value, exc)
        return {
            "status": "error",
            "correlation_id": correlation_id,
            "domain": route.domain.value,
            "response": (
                f"The {route.domain.value.replace('_', ' ')} agent is currently unavailable "
                "or returned an invalid response. Please try again shortly."
            ),
        }

    if result.kind == "input_required":
        return _pending_response(correlation_id, route.domain.value, result)

    logger.info("[%s] Delegation to %s succeeded (%d chars)", correlation_id, route.domain.value, len(result.text))
    return {"status": "success", "correlation_id": correlation_id, "domain": route.domain.value, "response": result.text}


def _handle_resume(resume_token: dict, correlation_id: str) -> dict:
    reference_id = resume_token.get("reference_id")
    domain = resume_token.get("domain")
    if not reference_id or not domain:
        return {"status": "error", "correlation_id": correlation_id, "response": "resume_token is missing required fields."}

    try:
        decision_record = get_decision(reference_id, correlation_id)
    except ApprovalAgentError as exc:
        logger.error("[%s] get_decision failed for %s: %s", correlation_id, reference_id, exc)
        return {"status": "error", "correlation_id": correlation_id, "response": "Could not reach the Approval Agent to check this request's status."}

    record_status = decision_record.get("status")
    if record_status == "PENDING":
        return {"status": "still_pending", "correlation_id": correlation_id, "domain": domain,
                "response": f"No human decision has been recorded yet for reference {reference_id}."}
    if record_status not in _DECISION_TO_ACTION:
        return {"status": "error", "correlation_id": correlation_id, "domain": domain,
                "response": f"Cannot resume: reference {reference_id} is {record_status}."}

    response_payload = {"decision": _DECISION_TO_ACTION[record_status]}
    if record_status == "APPROVED":
        response_payload["grant"] = decision_record.get("grant")
    if record_status == "INSTRUCTED":
        response_payload["instruction_text"] = decision_record.get("instruction_text")

    try:
        result = resume_delegated_agent(
            runtime_arn=resume_token["runtime_arn"],
            correlation_id=correlation_id,
            context_id=resume_token["context_id"],
            runtime_session_id=resume_token["runtime_session_id"],
            task_id=resume_token.get("task_id"),
            interrupt_id=resume_token["interrupt_id"],
            response=response_payload,
        )
    except DelegatedAgentError as exc:
        logger.error("[%s] Resume of %s failed: %s", correlation_id, reference_id, exc)
        return {"status": "error", "correlation_id": correlation_id, "domain": domain,
                "response": "Resuming the paused agent workflow failed. Please try again shortly."}

    if result.kind == "input_required":
        # e.g. an ADDITIONAL_INSTRUCTION resume led the agent to retry with
        # different arguments, which itself needed a fresh decision.
        return _pending_response(correlation_id, domain, result)

    logger.info("[%s] Resume of %s succeeded (%d chars)", correlation_id, reference_id, len(result.text))
    return {"status": "success", "correlation_id": correlation_id, "domain": domain, "response": result.text}


@app.entrypoint
def invoke(payload: dict) -> dict:
    correlation_id = str(uuid.uuid4())
    payload = payload or {}

    resume_token = payload.get("resume_token")
    if resume_token:
        return _handle_resume(resume_token, correlation_id)

    question = payload.get("prompt")
    if not isinstance(question, str) or not question.strip():
        logger.warning("[%s] Empty or invalid request payload: %r", correlation_id, payload)
        return {
            "status": "error",
            "correlation_id": correlation_id,
            "response": "Please provide a non-empty 'prompt' describing your question.",
        }

    return _handle_fresh_request(question, correlation_id)


if __name__ == "__main__":
    logger.info(
        "Orchestrator starting: api_security_agent=%s, agentic_security_agent=%s",
        AGENT_RUNTIME_ARNS[Domain.API_SECURITY],
        AGENT_RUNTIME_ARNS[Domain.AGENTIC_SECURITY],
    )
    app.run()
