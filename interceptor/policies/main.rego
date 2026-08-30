package gateway.authz

import rego.v1

# Phase 5: this policy is now only the *baseline* layer -- default-allow for
# everything (tools/list, initialize, and every tools/call), with the
# interceptor failing closed independently of OPA on any malformed event or
# OPA evaluation error (see handler.py). It is evaluated first, before the
# interceptor ever calls the Approval Agent.
#
# The Phase 4 rule that lived here (block any tools/call whose tool is
# sendFeedback) has been REMOVED, not weakened silently: per the Phase 5
# brief, "the interceptor does NOT own approval business logic" and "does
# NOT contain the sendFeedback approval rule." That rule now lives entirely
# inside the Approval Agent's deterministic ruleset (approval-agent/deterministic.py)
# as a real APPROVAL_REQUIRED decision (human must approve/deny), not an
# outright OPA BLOCK -- see docs/phase-context/phase-5-context.md
# ("Test 2 rescoping") for why this changes what Phase 4's original BLOCK
# test demonstrates.
#
# OPA is still a real, independent enforcement layer: it still runs on every
# request, still defaults to allow, and any future *purely mechanical*
# Rego-level rule (e.g. malformed method values, unsupported RPC methods)
# would still belong here -- rather than in the Approval Agent, which is
# reserved for rules that require deciding "does a human need to authorize
# this," not raw request-shape validation.
default allow := true

default block_reason := ""
