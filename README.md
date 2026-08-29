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
      REQUEST Interceptor Lambda
                 |
                 v
        Security controls:
          - Deterministic approval
          - Human-in-the-loop
          - OPA policy enforcement
                 |
                 v
      Existing remote MCP servers
       - mac-akto-api-mcp
       - mac-akto-ai-mcp
```

An Approval Agent/workflow handles approval, denial, additional human
instructions, and signed authorization grants. Workflow state lives in
DynamoDB; signed grants use AWS KMS.

## Repository layout

| Path | Purpose | Status |
|---|---|---|
| `infra/` | Terraform: state backend + per-environment stacks | Phase 1 (Gateway) deployed; Phase 2 (delegated agents) built, not yet deployed |
| `agents/` | Orchestrator, API Security Agent, Agentic Security Agent | API/Agentic Security Agents: Phase 2 code built, not yet deployed. Orchestrator: placeholder (Phase 3) |
| `gateway/` | AgentCore Gateway config, REQUEST interceptor Lambda, MCP targets | Placeholder |
| `policy/` | OPA policies | Placeholder |
| `approval-workflow/` | Approval Agent/workflow, DynamoDB + KMS | Placeholder |
| `scripts/` | Local dev/prereq helper scripts | Active |

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
