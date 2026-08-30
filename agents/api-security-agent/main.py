import logging
import os

from bedrock_agentcore.runtime import serve_a2a
from strands import Agent
from strands.multiagent.a2a.executor import StrandsA2AExecutor

from gateway_tool import GatewayApprovalHook, discover_gateway_tools

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")


def build_agent(context_id: str) -> Agent:
    # A fresh Agent per A2A context (StrandsA2AExecutor's recommended
    # agent_factory pattern) so concurrent conversations run independently
    # instead of serializing through one shared, deprecated `agent=` instance.
    logger.info("Building agent for A2A context_id=%s", context_id)
    return Agent(
        model=MODEL_ID,
        system_prompt=(
            "You are the API Security Agent in the Agent Security Lab, representing "
            "Akto's API Security and DAST (dynamic application security testing) domain. "
            "You have tools discovered directly from Akto's API MCP server -- use the "
            "search/get-page style tools to retrieve real Akto documentation before "
            "answering any question; never rely on your own prior knowledge alone. Give a "
            "clear, concise answer grounded in what the tool returns, and note that it is "
            "sourced from Akto's documentation. If, and only if, the user explicitly asks "
            "you to submit or send feedback about the documentation, use the sendFeedback "
            "tool with the feedback content they provided. Some tool calls may come back "
            "denied or asking for human input before they can proceed -- if that happens, "
            "clearly relay the reference and question to the user and stop; do not retry "
            "the same call yourself."
        ),
        tools=discover_gateway_tools(),
        # Phase 5: converts an interceptor APPROVAL_REQUIRED/HITL_REQUIRED
        # marker into a real Strands interrupt (A2A task state
        # input_required) and a resumed human decision into a grant-bearing
        # retry, a cancellation, or a surfaced instruction. One instance per
        # context (this function runs once per A2A context_id), so pending
        # state never leaks across concurrent conversations.
        hooks=[GatewayApprovalHook()],
    )


if __name__ == "__main__":
    logger.info(
        "API Security Agent starting: model=%s, mcp_target_prefix=%s, gateway_url=%s",
        MODEL_ID,
        os.environ.get("MCP_TARGET_PREFIX"),
        os.environ.get("GATEWAY_URL"),
    )
    serve_a2a(StrandsA2AExecutor(agent_factory=build_agent, enable_a2a_compliant_streaming=True))
