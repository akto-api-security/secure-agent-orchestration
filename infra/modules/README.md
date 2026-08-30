# Terraform modules

Reusable modules, each instantiated from `infra/environments/dev/main.tf`:

- `agentcore-gateway/` — Phase 1: AgentCore Gateway + MCP target wiring
- `agentcore-runtime-agent/` — Phase 2: delegated agents (instantiated twice:
  API Security Agent, Agentic Security Agent)
- `agentcore-orchestrator/` — Phase 3: Orchestrator
- `gateway-interceptor/` — Phase 4: REQUEST interceptor Lambda + OPA baseline
  policy
- `approval-agent/` — Phase 5: Approval Agent (deterministic + semantic
  rules, signed grants, human decision state)
