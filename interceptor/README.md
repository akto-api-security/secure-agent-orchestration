# Gateway Interceptor

A REQUEST interceptor Lambda for the AgentCore Gateway
(`asl-gateway-dev-xxxxxxxxxx`). It has an OPA/Rego baseline policy, and
routes every OPA-allowed `tools/call` to the Approval Agent
(`../approval-agent/`) for the actual authorization decision -- this
Lambda owns none of that decision logic itself (see this repo's internal
design notes under `../docs/` (gitignored, not part of the public repo),
"Locked responsibility model"), which also has
the original AWS research this design is based on. See
[../docs/architecture.md](../docs/architecture.md) ("Interceptor and
Approval Agent implementation") for the Terraform/IAM wiring.

```
Gateway (REQUEST interceptor, gateway-wide -- covers both MCP targets)
   |
   v
handler.py -- parse MCP interceptor event -> normalized OPA input
   |
   v
subprocess: bin/opa eval --data policies/main.rego --stdin-input data.gateway.authz
   |
   +-- deny (fail-closed only, see below)  -> BLOCK, Approval Agent never consulted
   +-- allow, method != tools/call          -> ALLOW directly (tools/list, initialize)
   +-- allow, method == tools/call          -> ask the Approval Agent
                                                  |
                                                  v
                                    {"decision": "ALLOW|BLOCK|APPROVAL_REQUIRED|HITL_REQUIRED", ...}
                                                  |
   +-- ALLOW              -> transformedGatewayRequest (grant stripped) -> MCP target runs
   +-- BLOCK               -> transformedGatewayResponse (JSON-RPC error) -> MCP target never runs
   +-- APPROVAL_REQUIRED /
       HITL_REQUIRED       -> transformedGatewayResponse (JSON-RPC error, reference_id +
                              human_question) -> MCP target never runs (yet)
```

## Why OPA as a subprocess, not a library

The real `opa` static binary is bundled in the Lambda package and invoked
as a subprocess (`opa eval --stdin-input`) -- no separate network service
(ruled out to keep the operational footprint minimal) and no WASM-runtime
dependency, while still using the actual OPA engine and letting local
tests run against the exact same binary/policy pair deployed in Lambda. It
costs one file (`bin/opa`, ~40-50MB, gitignored -- see "Get the OPA binary"
below) and one `subprocess.run` call per invocation.

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

## Interceptor event/response contract

Input (REQUEST interceptor, MCP target) -- only the fields this handler
reads are shown; see the interceptor context doc for the full schema:

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
field or error-body convention for this.** This project's own convention,
used here: a JSON-RPC 2.0 error envelope,
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

`error.code -32001` = policy/Approval-Agent block; `-32000` = interceptor
internal error (fail-closed path, see below). Two more,
non-terminal codes exist for a pending human decision: `-32010` =
`APPROVAL_REQUIRED`, `-32011` = `HITL_REQUIRED` -- same envelope shape,
`error.data` additionally carries `reference_id` and `human_question`.
Retrying with a grant: the caller adds a reserved argument key,
`_asl_grant`, to `params.arguments` -- the interceptor strips it before
ever forwarding `transformedGatewayRequest`, so the real MCP target never
sees it.

## Policies

**OPA is only the baseline layer.** `main.rego` is
`default allow := true` and nothing else -- the original Policy 2 (block
`sendFeedback`) was removed, since that business rule now belongs entirely
to the Approval Agent's deterministic ruleset
(`../approval-agent/deterministic.py`), per the explicit
requirement that this Lambda not own approval business logic. See this
repo's internal design notes under `../docs/` for the full reasoning.
OPA still runs on every request and is still fail-closed (below) -- a
future *purely mechanical* Rego-level rule would still belong here, not in
the Approval Agent.

## Fail-closed error handling

Any unexpected condition -- malformed event (no `mcp` key), missing/empty
request body, OPA binary missing or non-zero exit, unparseable OPA output,
or any other exception -- results in a BLOCK response (`error.code -32000`),
never a silent ALLOW, matching the required fail-closed default. No AWS
documentation was found suggesting a different required behavior on
interceptor Lambda error.

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

`_call_approval_agent` is monkeypatched in these unit tests (it's a real
AgentCore Runtime invocation over the network in production) --
`../approval-agent/tests/` covers that service's own logic.

## Manual end-to-end test against the deployed Lambda (before wiring to the Gateway)

Requires `APPROVAL_AGENT_RUNTIME_ARN` to already be set on the deployed
Lambda -- a `searchDocumentation` call now goes through to the
real Approval Agent, not just OPA:

```bash
aws lambda invoke --function-name asl-interceptor-dev \
  --cli-binary-format raw-in-base64-out \
  --payload '{"interceptorInputVersion":"1.0","mcp":{"gatewayRequest":{"body":{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"mac-akto-api-mcp___searchDocumentation","arguments":{"query":"OWASP API security"}}}}}}' \
  /tmp/interceptor-response.json
jq . /tmp/interceptor-response.json   # expect a transformedGatewayRequest (ALLOW)

aws lambda invoke --function-name asl-interceptor-dev \
  --cli-binary-format raw-in-base64-out \
  --payload '{"interceptorInputVersion":"1.0","mcp":{"gatewayRequest":{"body":{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"mac-akto-api-mcp___sendFeedback","arguments":{}}}}}}' \
  /tmp/interceptor-response.json
jq . /tmp/interceptor-response.json   # expect a transformedGatewayResponse with error.code -32010 (APPROVAL_REQUIRED)
```
