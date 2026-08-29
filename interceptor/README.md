# Gateway Interceptor (Phase 4)

A REQUEST interceptor Lambda for the Phase 1 AgentCore Gateway
(`asl-gateway-dev-xxxxxxxxxx`), enforcing an OPA/Rego policy before an MCP
tool call reaches either MCP target. See
[../docs/phase-context/phase-4-context.md](../docs/phase-context/phase-4-context.md)
for the full confirmed-vs-inferred AWS research this design is based on, and
[../docs/architecture.md](../docs/architecture.md) ("Phase 4 implementation")
for the Terraform/IAM wiring.

```
Gateway (REQUEST interceptor, gateway-wide -- covers both MCP targets)
   |
   v
handler.py -- parse MCP interceptor event -> normalized OPA input
   |
   v
subprocess: bin/opa eval --data policies/main.rego --stdin-input data.gateway.authz
   |
   v
{"allow": true|false, "block_reason": "..."}
   |
   +-- allow  -> transformedGatewayRequest (unmodified body)  -> MCP target runs
   +-- block  -> transformedGatewayResponse (JSON-RPC error)  -> MCP target never runs
```

## Why OPA as a subprocess, not a library

Three options were possible for a 48-hour demo (per the Phase 4 brief, "prefer
the smallest operational footprint" / "if running OPA directly inside Lambda
is technically appropriate, prefer that over adding another service"):

1. **OPA compiled to WASM, evaluated via a WASM runtime inside the Lambda** --
   real Rego semantics, but needs a WASM runtime dependency (e.g. `wasmtime`)
   with its own packaging/ABI concerns for a small demo.
2. **OPA as a separate network service** (ECS/Fargate sidecar, etc.) --
   explicitly ruled out by the brief ("Do NOT automatically create
   ECS/EKS/etc.").
3. **The real `opa` static binary, bundled in the Lambda package, invoked as
   a subprocess** (`opa eval --stdin-input`) -- no separate service, no WASM
   runtime dependency, uses the actual OPA engine (not a reimplementation),
   and is trivial to test locally with the exact same binary/policy pair
   that runs in Lambda.

Option 3 is what's implemented here. It costs one file (`bin/opa`, ~40-50MB,
gitignored -- see "Get the OPA binary" below) and one `subprocess.run` call
per invocation; no other service or runtime dependency.

## Files

```
interceptor/
├── handler.py            Lambda entrypoint (handler.handler)
├── policies/
│   ├── main.rego          Policy 1 (allow) + Policy 2 (block sendFeedback)
│   └── main_test.rego     opa test unit tests for the policy alone
├── tests/
│   └── test_handler.py    pytest, exercises handler.py -> real opa binary
├── build.sh               Downloads bin/opa (not committed -- see below)
└── .gitignore             bin/, *.zip, __pycache__/
```

## Interceptor event/response contract (confirmed against AWS docs)

Input (REQUEST interceptor, MCP target) -- only the fields this handler
reads are shown; see the phase-4 context doc for the full schema:

```json
{
  "interceptorInputVersion": "1.0",
  "mcp": {
    "gatewayRequest": {
      "body": {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "mac-akto-api-mcp___sendFeedback", "arguments": {}}}
    }
  }
}
```

ALLOW output -- pass the original body through unmodified:

```json
{"interceptorOutputVersion": "1.0",
 "mcp": {"transformedGatewayRequest": {"body": {"...": "original body"}}}}
```

BLOCK output -- `transformedGatewayResponse` short-circuits the gateway; the
MCP target is never called. **AWS does not document a fixed allow/deny
field or error-body convention for this** (confirmed by direct doc
inspection -- see phase-4 context doc, "Gap: no documented deny schema").
This project's own convention, used here: a JSON-RPC 2.0 error envelope,
HTTP `statusCode: 200` (the JSON-RPC error lives in the body, not the HTTP
status, matching how the Gateway itself reports MCP-level errors):

```json
{"interceptorOutputVersion": "1.0",
 "mcp": {"transformedGatewayResponse": {
   "statusCode": 200,
   "body": {"jsonrpc": "2.0", "id": 1,
            "error": {"code": -32001, "message": "Blocked by gateway policy",
                      "data": {"reason": "...", "correlation_id": "..."}}}}}}
```

`error.code -32001` = policy block; `-32000` = interceptor internal error
(fail-closed path, see below).

## Policies

- **Policy 1 (ALLOW):** everything not matched by Policy 2 -- `tools/list`,
  `initialize`, and `tools/call` against `searchDocumentation` or `getPage`
  on either Phase 1 MCP target.
- **Policy 2 (BLOCK):** any `tools/call` whose underlying tool name is
  `sendFeedback` (with either target prefix stripped). This is deterministic
  and demonstrable without inventing an artificial test flag: Phase 1's own
  `tools/list` probe found `sendFeedback` is the one write-capable tool on
  either MCP target (`searchDocumentation`/`getPage` are both
  `readOnlyHint: true`) -- the policy is "no write operations through this
  gateway."

## Fail-closed error handling

Any unexpected condition -- malformed event (no `mcp` key), missing/empty
request body, OPA binary missing or non-zero exit, unparseable OPA output,
or any other exception -- results in a BLOCK response (`error.code -32000`),
never a silent ALLOW. This matches the Phase 4 brief's default ("fail closed
... unless current AgentCore interceptor semantics require a different
response behavior") -- no AWS documentation was found suggesting a
different required behavior on interceptor Lambda error (see phase-4
context doc).

## Get the OPA binary (not committed to git)

```bash
./build.sh
```

Downloads **two** copies, since the deployment target (Lambda, linux/arm64)
and your dev machine are usually different platforms:

- `bin/opa` -- linux/arm64, what actually gets zipped into the Lambda
  deployment package (matches the Terraform module's
  `architectures = ["arm64"]`). Not runnable locally unless your machine
  *is* linux/arm64 -- that's expected, it's a deployment artifact.
- `bin/opa-local` -- matches your machine's OS/arch, for running the test
  suites below.

## Test locally

```bash
./build.sh                                          # once, fetches both binaries
bin/opa-local test policies/ -v                     # Rego unit tests (policy only)
OPA_BIN_PATH=bin/opa-local python3 -m pytest tests/ -v   # handler.py -> real opa subprocess
```

Both suites are the actual ALLOW/BLOCK evidence for Phase 4's two required
end-to-end tests, run against the real OPA engine and the real handler code
path -- not mocked policy decisions.

## Manual end-to-end test against the deployed Lambda (before wiring to the Gateway)

```bash
aws lambda invoke --function-name asl-interceptor-dev \
  --cli-binary-format raw-in-base64-out \
  --payload '{"interceptorInputVersion":"1.0","mcp":{"gatewayRequest":{"body":{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"mac-akto-api-mcp___sendFeedback","arguments":{}}}}}}' \
  /tmp/interceptor-response.json
jq . /tmp/interceptor-response.json   # expect a transformedGatewayResponse with error.code -32001
```
