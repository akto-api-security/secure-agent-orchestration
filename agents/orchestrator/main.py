import logging
import os
import uuid

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from a2a_client import DelegatedAgentError, invoke_delegated_agent
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


@app.entrypoint
def invoke(payload: dict) -> dict:
    correlation_id = str(uuid.uuid4())
    question = (payload or {}).get("prompt")

    if not isinstance(question, str) or not question.strip():
        logger.warning("[%s] Empty or invalid request payload: %r", correlation_id, payload)
        return {
            "status": "error",
            "correlation_id": correlation_id,
            "response": "Please provide a non-empty 'prompt' describing your question.",
        }

    question = question.strip()
    route = classify(question)
    logger.info(
        "[%s] Received question, classified as %s (matched=%s)",
        correlation_id,
        route.domain.value if route.domain else "ambiguous",
        route.matched_keywords,
    )

    if route.domain is None:
        return {
            "status": "clarification_needed",
            "correlation_id": correlation_id,
            "response": CLARIFICATION_MESSAGE,
        }

    runtime_arn = AGENT_RUNTIME_ARNS[route.domain]
    logger.info("[%s] Delegating to %s (%s)", correlation_id, route.domain.value, runtime_arn)

    try:
        answer = invoke_delegated_agent(
            runtime_arn=runtime_arn,
            question=question,
            correlation_id=correlation_id,
        )
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

    logger.info(
        "[%s] Delegation to %s succeeded (%d chars)", correlation_id, route.domain.value, len(answer)
    )
    return {
        "status": "success",
        "correlation_id": correlation_id,
        "domain": route.domain.value,
        "response": answer,
    }


if __name__ == "__main__":
    logger.info(
        "Orchestrator starting: api_security_agent=%s, agentic_security_agent=%s",
        AGENT_RUNTIME_ARNS[Domain.API_SECURITY],
        AGENT_RUNTIME_ARNS[Domain.AGENTIC_SECURITY],
    )
    app.run()
