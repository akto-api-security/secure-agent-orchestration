# Terraform modules

Reusable modules, each instantiated from `infra/environments/dev/main.tf`:

- `agentcore-gateway/` — AgentCore Gateway + MCP target wiring
- `agentcore-runtime-agent/` — delegated agents (instantiated twice:
  API Security Agent, Agentic Security Agent)
- `agentcore-orchestrator/` — Orchestrator
- `gateway-interceptor/` — REQUEST interceptor Lambda + OPA baseline
  policy
- `approval-agent/` — Approval Agent (deterministic + semantic
  rules, signed grants, human decision state)
