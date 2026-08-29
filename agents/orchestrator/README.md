# Orchestrator Agent

Phase 3 — Orchestrator. Runs on Amazon Bedrock AgentCore Runtime as an
**HTTP protocol** server (not A2A) -- it's the top-level entry point invoked
directly by a caller, not another A2A peer. It classifies each incoming
question and delegates to one of the two Phase 2 A2A agents.

```
POST /invocations {"prompt": "..."}
   |
   v
router.classify() -- deterministic keyword match
   |
   +-- api_security      -> a2a_client.invoke_delegated_agent(API Security Agent ARN)
   +-- agentic_security  -> a2a_client.invoke_delegated_agent(Agentic Security Agent ARN)
   +-- ambiguous         -> clarification response, no delegation
   |
   v  (boto3 bedrock-agentcore invoke_agent_runtime, A2A message/send JSON-RPC body)
Delegated Agent (AgentCore Runtime, A2A)
   |
   v
AgentCore Gateway -> MCP -> answer
   |
   v
A2A response (streamed text parts) -- reassembled here
   |
   v
{"status": "success", "domain": "...", "response": "...", "correlation_id": "..."}
```

## Why HTTP protocol, not A2A, for the orchestrator's own inbound interface

The Phase 3 brief only requires that *delegation* go over A2A -- it doesn't
require the orchestrator itself to be an A2A server. Nothing else in this
architecture calls the orchestrator as an A2A peer; it's invoked directly by
a user/test client. AgentCore Runtime's `protocol_configuration.server_protocol`
supports `HTTP | MCP | A2A` (confirmed via AWS's `ProtocolConfiguration` API
reference); `HTTP` is the simplest fit and needs no A2A executor/agent-card
machinery for a role that's never called as an A2A peer. The container
implements the standard HTTP protocol contract (`0.0.0.0:8080`,
`POST /invocations`, `GET /ping`) via `bedrock_agentcore.runtime.BedrockAgentCoreApp`
+ `@app.entrypoint` -- confirmed present in the same `bedrock-agentcore` SDK
version Phase 2 already pins, not a separate library.

## Why deterministic keyword routing, not an LLM call

The routing surface is exactly the two domain lists in the brief. A
substring match against those lists (`router.py`) is fully predictable,
requires no Bedrock model permission on the orchestrator's execution role,
and is directly traceable to the spec. This also narrows the orchestrator's
IAM footprint to exactly what the brief's "Important scope boundary" section
asks for: it never needs `bedrock:InvokeModel` or Gateway access, only
`bedrock-agentcore:InvokeAgentRuntime` on the two delegated agents
(`GetAgentCard` isn't granted either, since `a2a_client.py` never calls it).

## Files

| File | Purpose |
|---|---|
| `main.py` | `BedrockAgentCoreApp` entrypoint: validates input, calls `router.classify`, delegates via `a2a_client`, shapes the response. |
| `router.py` | `classify(question)` -- keyword match against the API Security / Agentic Security domain lists from the brief. Returns `None` domain (ambiguous) when there's no unambiguous match. |
| `a2a_client.py` | `invoke_delegated_agent(runtime_arn, question, correlation_id)` -- sends an A2A `message/send` JSON-RPC request via boto3's `bedrock-agentcore` `invoke_agent_runtime`, reassembles the streamed `artifacts[].parts[].text`, raises `DelegatedAgentError` on any failure. |
| `Dockerfile` | ARM64 image, listens on `0.0.0.0:8080` (HTTP protocol contract). |
| `requirements.txt` | `bedrock-agentcore`, `boto3` only -- no `strands`/`requests` needed (no LLM call, no raw HTTP to the Gateway). |

## Environment variables (set by Terraform, `infra/modules/agentcore-orchestrator`)

| Variable | Meaning |
|---|---|
| `API_SECURITY_AGENT_RUNTIME_ARN` | Full ARN of the Phase 2 API Security Agent's AgentCore Runtime. |
| `AGENTIC_SECURITY_AGENT_RUNTIME_ARN` | Full ARN of the Phase 2 Agentic Security Agent's AgentCore Runtime. |
| `AGENT_REGION` | Region used both to construct the `bedrock-agentcore` boto3 client and to sign the A2A call. **Not named `AWS_REGION`** -- see "Naming deviation from the brief" below. |
| `LOG_LEVEL` | Defaults to `INFO`. |

### Naming deviation from the brief (flagged, not silent)

The brief asks for an env var literally named `AWS_REGION`. Phase 2's
`gateway_tool.py` already documents that `AWS_REGION` is reserved by the
AgentCore Runtime platform itself, which is why it introduced `GATEWAY_REGION`
instead. This module follows that same precedent with `AGENT_REGION` rather
than fighting a name the platform may set/reserve out from under Terraform.
Functionally equivalent, just not the literal name from the brief.

The brief also names the identifiers `API_SECURITY_AGENT_RUNTIME_ID` /
`AGENTIC_SECURITY_AGENT_RUNTIME_ID`. boto3's `invoke_agent_runtime` requires
`agentRuntimeArn` (the full ARN), not the short ID, so this module uses
`..._RUNTIME_ARN` instead -- both Phase 2 agents' own Terraform outputs
already expose `agent_runtime_arn`, not a bare ID.

## Build and push the image

```bash
cd agents/orchestrator

ECR_REPO=$(cd ../../infra/environments/dev && terraform output -raw orchestrator_ecr_repository_url)

aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin "${ECR_REPO%/*}"

docker buildx build --platform linux/arm64 -t "${ECR_REPO}:latest" --push .
```

**zsh users:** always brace the variable (`${ECR_REPO}:latest`, not `$ECR_REPO:latest`). Unbraced, zsh parses the `:l` in `:latest` as its own "lowercase" history-style modifier and silently drops it, leaving a corrupted tag like `...-devatest` instead of `...-dev:latest` -- this isn't a Docker/Terraform bug, it's zsh-specific parameter-expansion behavior that bash doesn't have. Bracing avoids it entirely.

As with the Phase 2 agents, Terraform can't create the
`aws_bedrockagentcore_agent_runtime` resource until an image tagged
`:latest` exists in the ECR repo -- apply once for the repo, push the image,
apply again for the runtime.

## Test locally (no AWS needed except permission to invoke the two delegated agents)

```bash
pip install -r requirements.txt
export API_SECURITY_AGENT_RUNTIME_ARN="arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/asl_api_security_agent_dev-xxxxxxxxxx"
export AGENTIC_SECURITY_AGENT_RUNTIME_ARN="arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/asl_agentic_security_agent_dev-xxxxxxxxxx"
export AGENT_REGION=us-east-1
# AWS credentials with bedrock-agentcore:InvokeAgentRuntime/GetAgentCard on
# both agent ARNs above must be active in your shell.
python main.py
```

```bash
curl -s -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What does API security testing cover?"}' | jq .

curl -s -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is DAST?"}' | jq .

curl -s -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is prompt injection?"}' | jq .

curl -s -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "How does MCP security work?"}' | jq .

curl -s -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Tell me about security."}' | jq .

curl -s http://localhost:8080/ping | jq .
```

Expected `status` field per case: `success` / `success` / `success` /
`success` / `clarification_needed`. Each successful response's `domain`
field should read `api_security` for the first two and `agentic_security`
for the next two.

**Verified locally without AWS** (this session): `router.classify()` was run
directly against all 5 brief test questions plus the two extra examples in
the "Routing behavior" section, and `a2a_client.invoke_delegated_agent`'s
response-parsing/error paths (good response, JSON-RPC error envelope,
malformed JSON, missing `artifacts` shape, `ClientError`) were exercised
against fake `invoke_agent_runtime` responses -- all matched expected
behavior. **Not yet verified against the real deployed agents or the real
deployed orchestrator runtime** -- do that with the `aws bedrock-agentcore
invoke-agent-runtime` command in the Phase 3 context doc once the image is
built/pushed and `terraform apply` has run.

## Test the deployed agent

Same pattern as Phase 2: the runtime has no OAuth/JWT authorizer configured
here (HTTP protocol's default, unauthenticated-by-the-container path relies
on the standard SigV4-signed `InvokeAgentRuntime` control-plane call, same
as A2A runtimes), so a caller needs `bedrock-agentcore:InvokeAgentRuntime`
scoped to the orchestrator's runtime ARN -- Terraform creates that as a
standalone `asl-orchestrator-invoke-<env>` policy (not auto-attached).

Unlike the A2A agents, the orchestrator's own response isn't a JSON-RPC
envelope -- it's the plain JSON dict `main.py`'s entrypoint returns
(`{"status": ..., "domain": ..., "response": ..., "correlation_id": ...}`),
because its inbound protocol is HTTP, not A2A. The CLI writes that response
body directly to `<outfile>` (a required positional argument), and, as with
Phase 2's agents, `--payload` needs `fileb://<file>` rather than a raw JSON
string since it's a blob parameter:

```bash
echo '{"prompt": "What does API security testing cover?"}' > /tmp/orchestrator-payload.json

aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "$(cd ../../infra/environments/dev && terraform output -raw orchestrator_runtime_arn)" \
  --payload fileb:///tmp/orchestrator-payload.json \
  --region us-east-1 \
  /tmp/orchestrator-response.json

jq . /tmp/orchestrator-response.json
```
