package gateway.authz

import rego.v1

# Policy 1 (ALLOW) -- everything defaults to allowed: tools/list, initialize,
# and tools/call against any read-only tool (searchDocumentation, getPage on
# either Phase 1 MCP target).
default allow := true

default block_reason := ""

# Policy 2 (BLOCK) -- deterministic, demonstrable condition: block any
# tools/call whose underlying tool is "sendFeedback". Per Phase 1's
# tools/list probe, sendFeedback is the one write-capable tool on either
# MCP target (searchDocumentation and getPage are both readOnlyHint: true);
# this policy enforces "no write operations through this gateway" without
# needing an artificial test flag.
allow := false if {
	input.method == "tools/call"
	endswith(input.bare_tool_name, "sendFeedback")
}

block_reason := sprintf("write operation blocked: tool %q is not read-only", [input.tool_name]) if not allow
