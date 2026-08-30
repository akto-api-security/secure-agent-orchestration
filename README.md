# Agent Security Lab

Standalone AWS replica of a client's existing Amazon Bedrock AgentCore security
architecture, used to prototype and test security controls without touching
the client's environment.

**Akto integration (Guardrail, SDK, dashboard, enforcement layer) is explicitly
out of scope until a later phase.** This repo currently contains no Akto
components.

## Architecture (locked)

```
User
  |
  v
Orchestrator Agent
  | A2A
  +--------------------------------+
  |                                |
  v                                v
API Security Agent          Agentic Security Agent
(AgentCore Runtime)         (AgentCore Runtime)
  |                                |
  +--------------------------------+
                 |
                 v
        AgentCore Gateway
                 |
                 v
      REQUEST Interceptor Lambda  <---- verifies signed grants on resume
                 |
                 v
        OPA policy enforcement (baseline layer)
                 |
                 v
           Approval Agent (AgentCore Runtime)
        - deterministic approval (e.g. sendFeedback)
        - semantic HITL (e.g. DAST-related requests, real LLM call)
        - signed authorization grants (AWS KMS)
        - human decision state (DynamoDB)
                 |
                 v
     Human: approve / deny / additional instruction
                 |
                 v
      Existing remote MCP servers (only on ALLOW)
       - mac-akto-api-mcp
       - mac-akto-ai-mcp
```

The Approval Agent owns all approval/HITL decision-making; the interceptor
only routes to it and enforces the result. A human decides via
`scripts/approval_decide.py`; an approved request resumes with a signed,
single-use grant (KMS) that the interceptor verifies before allowing
execution. See `docs/phase-context/phase-5-context.md` for the full design.

## Repository layout

| Path | Purpose | Status |
|---|---|---|
| `infra/` | Terraform: state backend + per-environment stacks (Gateway, delegated agents, Orchestrator, interceptor, Approval Agent) | Deployed and live-tested, Phases 1-5 |
| `agents/` | Orchestrator, API Security Agent, Agentic Security Agent | Deployed and live-tested, Phases 2-5 |
| `interceptor/` | REQUEST interceptor Lambda + OPA baseline policy; routes to the Approval Agent | Deployed and live-tested, Phases 4-5 |
| `approval-agent/` | Approval Agent -- deterministic + semantic (LLM) approval rules, signed grants, human decision state | Deployed and live-tested, Phase 5 |
| `scripts/` | Local dev/prereq helper scripts, plus gitignored test/demo scripts that invoke real deployed AWS resources | Active |

## Prerequisites

- AWS CLI v2, authenticated (`aws sts get-caller-identity` succeeds)
- Terraform >= 1.10
- Python 3.13 (for later agent/Lambda phases)

Run `scripts/check_prereqs.sh` to verify these are in place.

## Conventions

- Region: `us-east-1`
- Resource naming: `asl-<component>-<env>`
- Tags on every resource: `Project=agent-security-lab`, `Environment`, `ManagedBy=terraform`, `Phase`
- No secrets or Terraform state committed to git (see `.gitignore`)
