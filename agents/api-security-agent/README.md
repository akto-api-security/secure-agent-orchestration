# API Security Agent

Phase 2 — Delegated Agents + A2A. Runs on Amazon Bedrock AgentCore Runtime as
an A2A server, representing Akto's **API Security / DAST** domain.

```
A2A task
   |
   v
Strands Agent (Bedrock model, this container)
   |  decides to call search_akto_api_security_docs
   v
gateway_tool.py -- SigV4 tools/list + tools/call
   |
   v
AgentCore Gateway (Phase 1: asl-gateway-dev-xxxxxxxxxx)
   |
   v
mac-akto-api-mcp  ->  https://docs.akto.io/~gitbook/mcp
   |
   v
A2A response (artifact text)
```

## Files

| File | Purpose |
|---|---|
| `main.py` | Builds the Strands `Agent` and starts it as an A2A server via `bedrock_agentcore.runtime.serve_a2a`. |
| `gateway_tool.py` | One `@tool`: SigV4-signs `tools/list`/`tools/call` requests to the Phase 1 Gateway, scoped to the `mac-akto-api-mcp` target. Discovers the search tool and its input schema at runtime rather than hardcoding a tool name. |
| `Dockerfile` | ARM64 container image, listens on `0.0.0.0:9000` (AgentCore's required A2A port/path). |
| `requirements.txt` | `strands-agents[a2a]`, `bedrock-agentcore`, `boto3`, `requests`. |

## Environment variables (set by Terraform, `infra/modules/agentcore-runtime-agent`)

| Variable | Meaning |
|---|---|
| `GATEWAY_URL` | Phase 1 Gateway MCP endpoint. |
| `GATEWAY_REGION` | Region for SigV4 signing (kept separate from `AWS_REGION`, which some managed compute platforms reserve). |
| `MCP_TARGET_PREFIX` | `mac-akto-api-mcp` -- the Gateway target namespace this agent is scoped to. |
| `BEDROCK_MODEL_ID` | Defaults to `us.anthropic.claude-haiku-4-5-20251001-v1:0` (verified ACTIVE in this account/region). |

## Build and push the image

AgentCore Runtime requires an **ARM64** image. Building on an Intel/AMD
machine needs Buildx cross-compilation.

```bash
cd agents/api-security-agent

# ECR repo URL comes from Terraform output (created before the agent runtime):
ECR_REPO=$(cd ../../infra/environments/dev && terraform output -raw api_security_agent_ecr_repository_url)

aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin "${ECR_REPO%/*}"

docker buildx build --platform linux/arm64 -t "$ECR_REPO:latest" --push .
```

Terraform can't create the `aws_bedrockagentcore_agent_runtime` resource
until an image tagged `:latest` exists in the repo it references -- apply
Terraform once to create the ECR repo, push the image, then apply again to
create the runtime.

## Test locally (no AWS needed except Gateway access)

```bash
pip install -r requirements.txt
export GATEWAY_URL="https://asl-gateway-dev-xxxxxxxxxx.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
export GATEWAY_REGION=us-east-1
export MCP_TARGET_PREFIX=mac-akto-api-mcp
# AWS credentials with bedrock-agentcore:InvokeGateway on the Phase 1 gateway
# and bedrock:InvokeModel must be active in your shell (e.g. via aws sso login).
python main.py
```

```bash
curl -X POST http://localhost:9000/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-001",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "Explain what API security testing covers in Akto."}],
        "messageId": "11111111-1111-1111-1111-111111111111"
      }
    }
  }' | jq .

curl http://localhost:9000/.well-known/agent-card.json | jq .
```

The server is started with `enable_a2a_compliant_streaming=True`, so a
successful response's `result.artifacts[0].parts` is a list of many small
streamed text deltas, not one blob -- reassemble the answer with:

```bash
... | jq -r '[.result.artifacts[0].parts[].text] | join("")'
```

**Verified locally** (2026-08-29, real AWS credentials, real Gateway/MCP
call, no mocking): this exact request against a local `python main.py` run
returned a 1637-character answer grounded in Akto's actual docs (OWASP Top
10 API coverage, REST/GraphQL/SOAP support, auth-token automation, custom
test editor, etc.), sourced via a real `tools/list` -> `mac-akto-api-mcp___searchDocumentation`
-> `tools/call` round trip through the Phase 1 Gateway.

## Test the deployed agent

The agent runtime is created with no `authorizer_configuration` block, which
leaves inbound A2A authorization on **AWS_IAM (SigV4)** -- this is an
implementation inference (see `infra/modules/agentcore-runtime-agent/runtime.tf`),
consistent with the Phase 1 Gateway's own choice to avoid standing up
Cognito, but **not yet confirmed by a real signed invoke**. Confirm it by
sending a SigV4-signed `InvokeAgentRuntime` call (e.g. with `awscurl`, same
tool used to verify the Gateway in Phase 1) against:

```
https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/<ESCAPED_AGENT_RUNTIME_ARN>/invocations/
```

using the JSON-RPC `message/send` body shown above. The identity used must
have `bedrock-agentcore:InvokeAgentRuntime` and `bedrock-agentcore:GetAgentCard`
scoped to this agent's runtime ARN -- Terraform creates that as a standalone
policy (`api_security_agent_invoke_policy_arn` output, mirroring
`asl-gateway-invoke-dev` from Phase 1) but does **not** attach it to
anything automatically. Attach it to whichever identity you test with.
