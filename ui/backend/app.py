"""Phase 6 lightweight demo UI backend -- FastAPI, calls only the
Orchestrator and Approval Agent AgentCore Runtimes (never the Gateway or
MCP directly, per the brief). Not a production frontend: a thin
presentation layer over the already-deployed, already-tested Phase 0-5
backend, mirroring exactly what scripts/demo_interactive.sh already does
via the AWS CLI.

Run via scripts/start-demo.sh, or directly:
    uvicorn backend.app:app --reload
from the ui/ directory, with ORCHESTRATOR_ARN / APPROVAL_AGENT_ARN / etc.
already exported (or a local infra/environments/dev checkout to fall back
to `terraform output`).
"""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import aws_clients
from .config import settings
from .verification import now_ms, verify_tool_execution

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Agent Security Lab -- Demo UI")

_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


@app.get("/")
def index():
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/api/health")
def health():
    return {
        "ready": settings.is_ready(),
        "orchestrator_arn": bool(settings.orchestrator_arn),
        "approval_agent_arn": bool(settings.approval_agent_arn),
        "region": settings.region,
    }


@app.post("/api/ask")
async def ask(request: Request):
    body = await request.json()
    prompt = (body or {}).get("prompt", "").strip()
    if not prompt:
        return JSONResponse({"status": "error", "response": "Please enter a question."}, status_code=400)

    start_ms = now_ms()
    try:
        result = aws_clients.ask_orchestrator(prompt)
    except aws_clients.AgentInvokeError as exc:
        logger.error("ask_orchestrator failed: %s", exc)
        return JSONResponse({"status": "error", "response": str(exc)}, status_code=502)

    result["_trigger_start_ms"] = start_ms
    return result


@app.post("/api/decide")
async def decide_route(request: Request):
    body = await request.json()
    reference_id = (body or {}).get("reference_id")
    decision = (body or {}).get("decision")
    instruction_text = (body or {}).get("instruction_text")
    resume_token = (body or {}).get("resume_token")

    if decision not in ("approve", "deny", "instruction"):
        return JSONResponse({"status": "error", "response": "decision must be approve, deny, or instruction."}, status_code=400)
    if not reference_id or not resume_token:
        return JSONResponse({"status": "error", "response": "reference_id and resume_token are required."}, status_code=400)

    try:
        decide_result = aws_clients.decide(reference_id, decision, instruction_text)
    except aws_clients.AgentInvokeError as exc:
        logger.error("decide failed: %s", exc)
        return JSONResponse({"status": "error", "response": str(exc)}, status_code=502)

    if decide_result.get("status") != "ok":
        # e.g. already decided, or a validation error from the Approval
        # Agent itself (see approval-agent/main.py's _handle_decide) --
        # surfaced as-is, not swallowed.
        return {"status": "error", "response": decide_result.get("reason", "Approval Agent rejected this decision."), "decide_result": decide_result}

    resume_start_ms = now_ms()
    try:
        resume_result = aws_clients.resume_orchestrator(resume_token)
    except aws_clients.AgentInvokeError as exc:
        logger.error("resume_orchestrator failed: %s", exc)
        return JSONResponse({"status": "error", "response": str(exc)}, status_code=502)

    resume_result["_trigger_start_ms"] = resume_start_ms
    resume_result["_decide_result"] = decide_result
    return resume_result


@app.get("/api/verify")
def verify(domain: str | None = None, tool_name: str | None = None, start_ms: int = 0, decision: str | None = None):
    verdict = verify_tool_execution(domain, tool_name, start_ms)
    return {"verdict": verdict.verdict, "detail": verdict.detail, "log_lines": verdict.log_lines, "decision": decision}
