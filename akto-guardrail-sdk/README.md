# Akto Guardrail SDK

A lightweight, dependency-free Python client for the Akto Guardrail Engine.
It sends a tool call to your Guardrail Engine deployment and returns a
normalized decision: `ALLOW` or `BLOCK`.

## What this is

This package has no dependencies beyond the Python standard library, and
no dependency on any particular runtime, cloud, or framework. It's a plain
importable package that does one thing: evaluate a tool call against your
Guardrail Engine and return a decision. It does not execute anything, does
not enforce its own decision, and does not talk to any other service.

**Deployment model.** This SDK is the same code for every customer. What's
different per customer is configuration: your own Guardrail Engine URL and
credential, pointing at your own dedicated deployment. See "Configuration"
below.

## Installation

No `pip install` step is required. Copy `akto_guardrail_sdk/` into your
project, or add this directory to your `PYTHONPATH`.

## Quick start

```python
from akto_guardrail_sdk import AktoGuardrailClient, AktoGuardrailConfig, RequestContext, Decision

config = AktoGuardrailConfig.from_env()
client = AktoGuardrailClient(config)

decision = client.evaluate(RequestContext(
    correlation_id="abc-123",
    tool_name="my-mcp-target___searchDocumentation",
    bare_tool_name="searchDocumentation",
    mcp_target="my-mcp-target",
    tool_arguments={"query": "..."},
    requesting_agent="arn:aws:iam::...",   # optional
    session_id="session-xyz",               # optional
))

if decision.decision == Decision.ALLOW:
    ...   # proceed with your own existing enforcement/execution
elif decision.decision == Decision.BLOCK:
    ...   # deny, using your own existing deny/error path
```

That's the whole integration surface: construct a `RequestContext` from
data you already have, call `evaluate()`, and act on `decision.decision`.
HTTP, headers, authentication, serialization, and error handling are all
handled internally.

## Configuration

```python
from akto_guardrail_sdk import AktoGuardrailConfig

config = AktoGuardrailConfig.from_env()  # reads AKTO_GUARDRAIL_* env vars

# or construct directly:
config = AktoGuardrailConfig(
    base_url="https://<your Guardrail Engine deployment>",
    api_key="<your credential, if required>",
    timeout_seconds=5,
)
```

| Env var | Required | Default | Notes |
|---|---|---|---|
| `AKTO_GUARDRAIL_URL` | yes | — | Your Guardrail Engine deployment's base URL. |
| `AKTO_GUARDRAIL_API_KEY` | no | none | Your credential, if your deployment requires one. Sent as a header only — never in the request body, never logged. |
| `AKTO_GUARDRAIL_API_KEY_HEADER` | no | `Authorization` | Override the header name the credential is sent in. |
| `AKTO_GUARDRAIL_TIMEOUT_SECONDS` | no | `5` | Per-call HTTP timeout. |
| `AKTO_GUARDRAIL_ENVIRONMENT` | no | none | Free-form identifier, for your own logging only. |
| `AKTO_GUARDRAIL_ACCOUNT_ID` | no | derived from `AKTO_GUARDRAIL_URL` | Your Guardrail Engine URL already encodes your account ID (e.g. `https://1234567890-guardrails.akto.io`) — this is derived from it automatically. Set this only to override that, or if your URL doesn't follow that pattern. |

These are set directly as plain environment variables in your interceptor's
own runtime config (e.g. a Lambda's environment block, a `.env` file, or a
container's env config) — the same way you'd configure any other external
service credential in your deployment.

## Decision model

```python
class Decision(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
```

Currently, `evaluate()` returns `ALLOW` or `BLOCK`. `APPROVAL_REQUIRED` is
reserved in the type for forward compatibility but is not returned by this
version of the SDK.

- **ALLOW** — proceed with your own existing enforcement/execution. This
  SDK does not execute anything itself.
- **BLOCK** — deny, using your own existing deny/error path. `reason`
  carries a human-readable explanation. This SDK does not enforce the
  decision itself; it only reports it.

## Error handling

`evaluate()` either returns a `GuardrailDecision` or raises an
`AktoGuardrailError` subclass — it never returns a decision on a failure
path, and never treats a failure as ALLOW.

```python
from akto_guardrail_sdk import AktoGuardrailError

try:
    decision = client.evaluate(request_context)
except AktoGuardrailError as exc:
    # timeout, HTTP failure, auth failure, or malformed response — treat as BLOCK
    ...
```

| Exception | Raised when |
|---|---|
| `AktoGuardrailConfigError` | Missing/invalid configuration. |
| `AktoGuardrailTimeoutError` | The Guardrail Engine didn't respond within the configured timeout. |
| `AktoGuardrailHTTPError` | A non-2xx HTTP response, or the connection failed. Carries `.status_code` when known. |
| `AktoGuardrailAuthenticationError` | The Guardrail Engine rejected the configured credentials. |
| `AktoGuardrailMalformedResponseError` | The response couldn't be parsed. |
| `AktoGuardrailUnexpectedDecisionError` | Reserved for forward compatibility. |

All inherit from `AktoGuardrailError`. This SDK does not retry failed
calls — a failed attempt raises immediately.

## Security notes

- Credentials are read from configuration only, never hardcoded, never
  logged, and never placed in the request body.
- `tool_arguments` is sent to your Guardrail Engine as-is. Don't pass
  secrets or credentials through it.
- `AKTO_GUARDRAIL_API_KEY` is currently supplied as a plain environment
  variable, which means it will sit in plaintext wherever your deployment
  stores its environment configuration (e.g. Terraform state, a `.env`
  file). If you need a secrets-manager-backed credential instead, resolve
  it to a plain string yourself before constructing `AktoGuardrailConfig`
  — its interface doesn't change either way.

## Testing

```bash
cd akto-guardrail-sdk
python3 -m pytest tests/test_client.py -v
```

Every test mocks the HTTP transport — no real network calls. To test
against a real deployment, see `tests/test_real_guardrail_integration.py`
(skipped by default).

## What this SDK does not do

- Execute or call any tool / downstream action.
- Enforce its own decision — it only returns one.
- Implement policy engines, approval workflows, or orchestration of any
  kind — that logic stays entirely on your side.
- Talk to any service other than the one configured `AKTO_GUARDRAIL_URL`.

## Files

```
akto-guardrail-sdk/
├── README.md
├── akto_guardrail_sdk/
│   ├── __init__.py       Public exports
│   ├── client.py          AktoGuardrailClient
│   ├── config.py           AktoGuardrailConfig
│   ├── contract.py          Request/response wire format
│   ├── exceptions.py         Error hierarchy
│   └── models.py              RequestContext / GuardrailDecision / Decision
├── examples/
│   └── basic_usage.py    Runnable example
└── tests/
    ├── test_client.py                     Unit tests (mocked transport)
    └── test_real_guardrail_integration.py Real-network test, skipped by default
```
