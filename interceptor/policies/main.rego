package gateway.authz

import rego.v1

# Baseline layer only: default-allow for everything. The interceptor fails
# closed independently of OPA on any malformed event or eval error (see
# handler.py), and OPA is evaluated before the Approval Agent is consulted.
#
# sendFeedback's block rule was intentionally removed from here, not
# silently weakened -- it now lives in the Approval Agent's deterministic
# ruleset (approval-agent/deterministic.py) as an APPROVAL_REQUIRED
# decision requiring human approve/deny, rather than an outright OPA BLOCK.
# Any future *purely mechanical* Rego-level rule (malformed method values,
# unsupported RPC methods) still belongs here; rules that decide "does a
# human need to authorize this" belong in the Approval Agent instead.
default allow := true

default block_reason := ""
