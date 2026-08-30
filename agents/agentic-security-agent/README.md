# Agentic Security Agent

A delegated agent, invoked over A2A. Runs on Amazon Bedrock AgentCore Runtime as
an A2A server, representing Akto's **Atlas / Argus / agentic security / MCP
security / A2A security** domain.

```
A2A task
   |
   v
Strands Agent (Bedrock model, this container)
   |  decides to call search_akto_agentic_security_docs
   v
gateway_tool.py -- SigV4 tools/list + tools/call
   |
   v
AgentCore Gateway (asl-gateway-dev-xxxxxxxxxx)
   |
   v
mac-akto-ai-mcp  ->  https://ai-security-docs.akto.io/~gitbook/mcp
   |
   v
A2A response (artifact text)
```

## Files

| File | Purpose |
|---|---|
| `main.py` | Builds the Strands `Agent` and starts it as an A2A server via `bedrock_agentcore.runtime.serve_a2a`. |
| `gateway_tool.py` | SigV4-signs `tools/list`/`tools/call` requests to the Gateway, scoped to the `mac-akto-ai-mcp` target. Discovers every tool the Gateway lists for this target (not just one hardcoded search tool) and exposes each as a Strands `MCPAgentTool` -- currently `searchDocumentation`, `getPage`, and `sendFeedback`. Cross-target tools are excluded by the `MCP_TARGET_PREFIX` namespace filter. |
| `Dockerfile` | ARM64 container image, listens on `0.0.0.0:9000` (AgentCore's required A2A port/path). |
| `requirements.txt` | `strands-agents[a2a]`, `bedrock-agentcore`, `boto3`, `requests`. |

## Environment variables (set by Terraform, `infra/modules/agentcore-runtime-agent`)

| Variable | Meaning |
|---|---|
| `GATEWAY_URL` | Gateway MCP endpoint. |
| `GATEWAY_REGION` | Region for SigV4 signing (kept separate from `AWS_REGION`, which some managed compute platforms reserve). |
| `MCP_TARGET_PREFIX` | `mac-akto-ai-mcp` -- the Gateway target namespace this agent is scoped to. |
| `BEDROCK_MODEL_ID` | Defaults to `us.anthropic.claude-haiku-4-5-20251001-v1:0` (verified ACTIVE in this account/region). |

## Build and push the image

AgentCore Runtime requires an **ARM64** image. Building on an Intel/AMD
machine needs Buildx cross-compilation.

```bash
cd agents/agentic-security-agent

# ECR repo URL comes from Terraform output (created before the agent runtime):
ECR_REPO=$(cd ../../infra/environments/dev && terraform output -raw agentic_security_agent_ecr_repository_url)

aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin "${ECR_REPO%/*}"

docker buildx build --platform linux/arm64 -t "${ECR_REPO}:latest" --push .
```

**zsh users:** brace the variable (`${ECR_REPO}:latest`, not `$ECR_REPO:latest`) -- unbraced, zsh parses the `:l` in `:latest` as its own "lowercase" modifier and drops it, corrupting the tag into `...-devatest`-style garbage instead of `...-dev:latest`. Confirmed while debugging the same pattern in the orchestrator build.

Terraform can't create the `aws_bedrockagentcore_agent_runtime` resource
until an image tagged `:latest` exists in the repo it references -- apply
Terraform once to create the ECR repo, push the image, then apply again to
create the runtime.

## Rebuild and redeploy an already-running runtime

**Overwriting the `:latest` tag in ECR does not make the already-deployed
AgentCore Runtime pick up the new image.** `container_uri` is pinned to that
tag *string*; the running runtime keeps whatever digest it resolved to at
creation/last-update time, and `terraform apply` won't detect a change either
(Terraform only diffs the configured string, which hasn't changed). The
AWS-supported way to force it is `UpdateAgentRuntime` (**not** `terraform
apply`, and not recreating the runtime) -- same `agent-runtime-id`, same ARN,
same IAM policies, just a new `agentRuntimeArtifact`. Pin to the pushed
image's digest rather than `:latest` so the call is unambiguous:

```bash
# 1. Build and push as above, then grab the digest of what was just pushed
DIGEST=$(aws ecr describe-images --repository-name asl-agentic-security-agent-dev \
  --image-ids imageTag=latest --region us-east-1 \
  --query 'imageDetails[0].imageDigest' --output text)

# 2. Update the existing runtime in place (values below match the currently
#    deployed config -- confirm with `get-agent-runtime` first if anything
#    else may have changed since):
aws bedrock-agentcore-control update-agent-runtime \
  --agent-runtime-id asl_agentic_security_agent_dev-xxxxxxxxxx \
  --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"${ECR_REPO}@${DIGEST}\"}}" \
  --role-arn arn:aws:iam::000000000000:role/asl-agentic-security-agent-execution-dev \
  --network-configuration networkMode=PUBLIC \
  --protocol-configuration serverProtocol=A2A \
  --environment-variables '{"BEDROCK_MODEL_ID":"us.anthropic.claude-haiku-4-5-20251001-v1:0","GATEWAY_REGION":"us-east-1","GATEWAY_URL":"https://asl-gateway-dev-xxxxxxxxxx.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp","MCP_TARGET_PREFIX":"mac-akto-ai-mcp"}' \
  --region us-east-1

# 3. Confirm it actually took: status READY, containerUri now ends in
#    @sha256:<the digest above>, agentRuntimeVersion incremented.
aws bedrock-agentcore-control get-agent-runtime \
  --agent-runtime-id asl_agentic_security_agent_dev-xxxxxxxxxx --region us-east-1
```

After this, send one fresh test invoke (see "Test the deployed agent" below)
and check CloudWatch: the old `UserWarning`/`DeprecationWarning` about a
shared `Agent` instance and non-compliant A2A streaming should be gone --
current source already has the `agent_factory=`/`enable_a2a_compliant_streaming=True`
fix, this just confirms the *deployed* image actually reflects it.

Terraform's own state still says `container_uri = "...:latest"` after this --
expected, not a bug. A future `terraform apply` will reconcile it back to the
`:latest` string (harmless, since that tag still points at the same image),
but review the plan diff before applying rather than assuming it's a no-op.

## Test locally (no AWS needed except Gateway access)

```bash
pip install -r requirements.txt
export GATEWAY_URL="https://asl-gateway-dev-xxxxxxxxxx.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
export GATEWAY_REGION=us-east-1
export MCP_TARGET_PREFIX=mac-akto-ai-mcp
# AWS credentials with bedrock-agentcore:InvokeGateway on the gateway
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
        "parts": [{"kind": "text", "text": "What is prompt injection and how does Akto test for it?"}],
        "messageId": "22222222-2222-2222-2222-222222222222"
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

## Test the deployed agent

The agent runtime is created with no `authorizer_configuration` block, which
leaves inbound A2A authorization on **AWS_IAM (SigV4)** -- this is an
implementation inference (see `infra/modules/agentcore-runtime-agent/runtime.tf`),
consistent with the Gateway's own choice to avoid standing up
Cognito, but **not yet confirmed by a real signed invoke**. Confirm it by
sending a SigV4-signed `InvokeAgentRuntime` call (e.g. with `awscurl`, same
tool used to verify the Gateway originally) against:

```
https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/<ESCAPED_AGENT_RUNTIME_ARN>/invocations/
```

using the JSON-RPC `message/send` body shown above. The identity used must
have `bedrock-agentcore:InvokeAgentRuntime` and `bedrock-agentcore:GetAgentCard`
scoped to this agent's runtime ARN -- Terraform creates that as a standalone
policy (`agentic_security_agent_invoke_policy_arn` output, mirroring
`asl-gateway-invoke-dev`) but does **not** attach it to
anything automatically. Attach it to whichever identity you test with.
