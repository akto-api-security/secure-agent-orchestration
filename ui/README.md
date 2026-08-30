# Demo UI

Phase 6 -- a small, non-production presentation layer over the already
deployed and live-tested Phase 0-5 backend. FastAPI backend + vanilla
HTML/JS frontend, no framework. It calls only the Orchestrator and Approval
Agent AgentCore Runtimes (`ui/backend/aws_clients.py`) -- it never talks to
the Gateway or MCP directly, and it cannot bypass OPA or the Approval Agent
(there is no code path here that does).

`scripts/test_approval_flow.sh` / `scripts/test_hitl_flow.sh` /
`scripts/demo_interactive.sh` (gitignored, internal-only) are unchanged and
still the right tools for a scripted CLI demo or debugging -- this UI is an
additional presentation layer, not a replacement.

## Run it

```bash
scripts/start-demo.sh            # resolves ARNs from terraform output, launches on :8000
```

or manually:

```bash
export ORCHESTRATOR_ARN="..."      # from `terraform output orchestrator_runtime_arn`
export APPROVAL_AGENT_ARN="..."
export API_AGENT_ARN="..."
export AGENTIC_AGENT_ARN="..."
export INTERCEPTOR_LOG_GROUP="..."
cd ui
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
python3 -m uvicorn backend.app:app --reload
```

Then open http://localhost:8000. Whatever AWS credentials are active in
your shell need `bedrock-agentcore:InvokeAgentRuntime` on the Orchestrator
and Approval Agent runtimes (the existing `asl-orchestrator-invoke-<env>` /
`asl-approval-agent-invoke-<env>` Terraform outputs), plus, optionally,
`logs:FilterLogEvents` on the delegated agents' log groups for the "actual
execution" verification panel (degrades to `UNKNOWN` without it, same as
`demo_interactive.sh`'s CloudWatch steps).

## What "actual execution" means

The agent's own final text is one thing; whether the real MCP tool actually
ran is another (see `docs/architecture.md`, Phase 5's tool_name/execution
verification). The "Actual execution" panel only appears once a tool name
is known (an approval/HITL request) and reports one of:

- `EXECUTED` -- a real `"Tool call succeeded: tool=..."` line was found in
  the delegated agent's own CloudWatch log group after the resume.
- `NOT EXECUTED / BLOCKED` -- no such line was found (expected after a
  DENY, or a DENY-treated unrecognized action).
- `UNKNOWN` -- the log group couldn't be read (missing permission) or logs
  hadn't propagated yet within the check window.

It never guesses beyond those three states.

## Demo scenarios -> UI actions

| # | Scenario | UI action |
|---|---|---|
| 1 | Normal API Security request | Ask an API-security-domain question |
| 2 | Normal Agentic Security request | Ask an Atlas/Argus/agentic-domain question |
| 3 | sendFeedback deterministic approval | Ask it to submit feedback, click APPROVE |
| 4 | sendFeedback denial | Same, click DENY |
| 5 | DAST HITL | Ask a DAST-related question |
| 6 | DAST approval | ...click APPROVE |
| 7 | DAST denial | ...click DENY |
| 8 | DAST additional instruction | ...enter instruction text, click SEND INSTRUCTION |
| 9 | OPA ALLOW | Any of the above that isn't a malformed request -- OPA's baseline layer runs and allows on every real request (see `interceptor/policies/main.rego`) |
| 10 | OPA BLOCK | Not reachable through a normal prompt today -- OPA's Phase 4 `sendFeedback`-block rule was intentionally removed in Phase 5 (that decision now belongs to the Approval Agent, see `docs/architecture.md`); OPA's only remaining behavior is fail-closed on a malformed/unsupported request, which this UI cannot construct through the Orchestrator's own input validation. Flagged here rather than faked. |
