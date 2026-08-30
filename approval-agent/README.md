# Approval Agent (Phase 5)

Owns all approval/human-in-the-loop business logic for this project. Runs
as its own AWS Bedrock AgentCore Runtime (HTTP protocol -- the same pattern
already used and live-tested for the Phase 3 Orchestrator), invoked by the
Phase 4 interceptor Lambda for every OPA-allowed `tools/call`, and by a
human's own CLI/API calls to record a decision.

See [../docs/phase-context/phase-5-context.md](../docs/phase-context/phase-5-context.md)
for the full design (locked responsibility model, grant mechanism, HITL
resume mechanism, AWS capabilities verified vs. inferred) and
[../docs/architecture.md](../docs/architecture.md) ("Phase 5 implementation")
for the Terraform/IAM wiring.

```
Interceptor
   |  action=authorize {correlation_id, tool_name, target, arguments, grant?}
   v
main.py
   |
   +-- grant present?      -> grants.verify_grant() + state (KMS + DynamoDB, no LLM)
   +-- deterministic.py     -> sendFeedback? -> APPROVAL_REQUIRED (no LLM)
   +-- semantic.py          -> DAST-related? -> HITL_REQUIRED (real Bedrock model call)
   +-- otherwise            -> ALLOW
```

## Files

| File | Purpose |
|---|---|
| `main.py` | `BedrockAgentCoreApp` entrypoint. Dispatches on `action`: `authorize` (interceptor), `decide` (human), `get_decision` (orchestrator resume / status check). |
| `deterministic.py` | Rules that never call an LLM. Currently: sendFeedback always requires approval. Appending a rule here needs no interceptor change. |
| `semantic.py` | Rules that call a real Bedrock model via tool-forced structured output (`toolChoice`), never free-text parsing. Currently: DAST-relatedness. |
| `grants.py` | Issues/verifies KMS-signed (`ECC_NIST_P256`, Sign/Verify) short-lived grants binding a decision to one exact tool/target/arguments hash. |
| `state.py` | DynamoDB-backed pending/decided state, all writes conditional (idempotency/replay-prevention boundary). |

## Actions

**`authorize`** -- called by the interceptor for every OPA-allowed `tools/call`.
```json
{"action": "authorize", "correlation_id": "...", "method": "tools/call",
 "tool_name": "mac-akto-api-mcp___sendFeedback", "bare_tool_name": "sendFeedback",
 "target": "mac-akto-api-mcp", "arguments": {"...": "..."}, "grant": null,
 "requesting_principal": "arn:...|null"}
```
Returns `{"decision": "ALLOW|BLOCK|APPROVAL_REQUIRED|HITL_REQUIRED", "reason": "...",
"decision_mode": "deterministic|semantic|grant_verification", "llm_invoked": bool,
"approval_id"/"hitl_id": "...", "human_question": "..."}`.

**`decide`** -- called by a human (see `scripts/approval_decide.py`, gitignored).
```json
{"action": "decide", "reference_id": "appr-...", "decision": "approve|deny|instruction",
 "instruction_text": "... (instruction only, HITL requests only)", "approver": "optional"}
```
Returns `{"status": "ok", "reference_id": "...", "decision": "...", "kind": "approval|hitl", "grant": "...|null"}`.
Conditional on the record still being PENDING -- a second `decide` call for
the same reference_id returns an error instead of silently overwriting the
first decision (see state.py's `AlreadyDecidedError`).

**`get_decision`** -- read-only status/decision lookup (used by the
orchestrator to resume a paused delegated-agent task, and safe to poll
repeatedly).
```json
{"action": "get_decision", "reference_id": "appr-..."}
```
Returns `{"status": "PENDING|APPROVED|DENIED|INSTRUCTED|NOT_FOUND", "kind": "...",
"decision": "...", "grant": "...|null", "instruction_text": "...|null", ...}`.

## Why this runs on AgentCore Runtime, not a Lambda

The delegated agents, the Orchestrator, and this component all run on
AgentCore Runtime for architectural consistency, and because "Approval
Agent" is a real, first-class component of the client's own diagram (not
just a policy check) -- see the phase-5-context doc for the full reasoning,
including the AWS-capability research this design is based on (there is no
native AgentCore approval/HITL mechanism to use instead -- confirmed by
direct research this session, not assumed).

## Local testing

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest boto3
.venv/bin/python -m pytest tests/ -v
```

All state (DynamoDB) and crypto (KMS) calls are faked in tests -- see
`tests/test_state.py`/`tests/test_grants.py` for the fakes, and
`tests/test_main.py` for the full deterministic-approval and grant-replay
chains exercised end-to-end against them.
