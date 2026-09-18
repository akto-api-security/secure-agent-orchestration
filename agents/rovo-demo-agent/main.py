import logging
import os
import uuid

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent

from gateway_tool import discover_gateway_tools

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")

SYSTEM_PROMPT = (
    "You are a backlog organization assistant for Jira and Confluence. You help "
    "users prioritize tickets, read uploaded guides, search internal tickets and "
    "wiki pages, and summarize recommended updates. Use read_uploaded_document "
    "when the user references an uploaded file or guide. Use search_jira_tickets "
    "and search_confluence_pages to gather context before recommending changes. "
    "Use open_url only when the user or a trusted internal link explicitly "
    "requires opening a URL. If a tool call comes back blocked or denied, tell "
    "the user the tool was blocked by policy and stop; do not invent a substitute "
    "result."
)


@app.entrypoint
def invoke(payload: dict) -> dict:
    correlation_id = str(uuid.uuid4())
    payload = payload or {}
    question = payload.get("prompt")
    if not isinstance(question, str) or not question.strip():
        return {
            "status": "error",
            "correlation_id": correlation_id,
            "response": "Please provide a non-empty 'prompt'.",
        }

    logger.info("[%s] Received prompt (%d chars)", correlation_id, len(question))
    agent = Agent(
        model=MODEL_ID,
        system_prompt=SYSTEM_PROMPT,
        tools=discover_gateway_tools(),
    )
    result = agent(question.strip())
    text = str(result)
    logger.info("[%s] Agent finished (%d chars)", correlation_id, len(text))
    return {
        "status": "success",
        "correlation_id": correlation_id,
        "response": text,
    }


if __name__ == "__main__":
    logger.info(
        "Rovo demo agent starting: model=%s, gateway_url=%s, mcp_target_prefix=%s",
        MODEL_ID,
        os.environ.get("GATEWAY_URL"),
        os.environ.get("MCP_TARGET_PREFIX"),
    )
    app.run()
