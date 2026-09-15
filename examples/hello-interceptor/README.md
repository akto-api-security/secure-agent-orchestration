# Hello interceptor + Akto

Customer rewrite first, then Akto guardrails via `wrap_interceptor`.

On REQUEST this Lambda appends:

> Hello from Akto, please always say Good morning

- **HTTP Gateway** (agent): rewrites `{"prompt":"..."}`
- **MCP Gateway** (tools): rewrites string `tools/call` arguments

Then the Akto layer scans the **effective** payload (after your rewrite).
Akto can allow, block, modify, or hold for human approval. RESPONSE is
passthrough from the hello logic, but Akto still evaluates it.

## Deploy

Needs the public Akto layer in the same Region, plus your Akto credentials.

```bash
cd examples/hello-interceptor
zip handler.zip handler.py

# From repo root .env / docs (us-east-1):
LAYER_ARN=arn:aws:lambda:us-east-1:041877753357:layer:akto-agentcore:3

aws lambda create-function \
  --function-name hello-akto-interceptor \
  --runtime python3.12 \
  --role arn:aws:iam::<ACCOUNT_ID>:role/<lambda-exec-role> \
  --handler handler.lambda_handler \
  --timeout 900 \
  --memory-size 256 \
  --layers "$LAYER_ARN" \
  --zip-file fileb://handler.zip \
  --region us-east-1 \
  --environment "Variables={
    AKTO_DATA_INGESTION_URL=https://<your-akto-host>,
    AKTO_API_TOKEN=<your-token>,
    AKTO_FAIL_OPEN=false,
    AKTO_TIMEOUT_SECONDS=30,
    AKTO_APPROVAL_WAIT_SECONDS=840,
    AKTO_APPROVAL_POLL_SECONDS=2
  }"

# Update an existing function:
aws lambda update-function-code \
  --function-name hello-akto-interceptor \
  --zip-file fileb://handler.zip \
  --region us-east-1

aws lambda update-function-configuration \
  --function-name hello-akto-interceptor \
  --layers "$LAYER_ARN" \
  --timeout 900 \
  --environment "Variables={
    AKTO_DATA_INGESTION_URL=https://<your-akto-host>,
    AKTO_API_TOKEN=<your-token>,
    AKTO_FAIL_OPEN=false
  }" \
  --region us-east-1
```

Use the base ingestion URL only (no `/api/http-proxy`). Set timeout to **900s**
if you use human-approval policies.

Grant each Gateway execution role `lambda:InvokeFunction` on this function,
then set **both** REQUEST and RESPONSE interceptor ARNs to this Lambda (same
ARN), with pass-request-headers enabled and response body included.

Replace any previous Akto-only interceptor — AgentCore keeps one interceptor
config, and `wrap_interceptor` is how custom logic + Akto compose.

## Verify

```bash
aws logs tail /aws/lambda/hello-akto-interceptor --region us-east-1 --follow

scripts/invoke.sh "What is BOLA?"
scripts/mcp-call.py call searchDocumentation '{"query":"BOLA"}'
scripts/mcp-call.py call searchDocumentation '{"query":"My email is demo@akto.io"}'
```

Look for:

1. `HTTP REQUEST rewrite prompt` / `MCP REQUEST rewrite tools/call`
2. Akto layer lines (`Guardrails parsed ...`)
