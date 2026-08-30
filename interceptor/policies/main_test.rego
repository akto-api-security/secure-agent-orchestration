package gateway.authz_test

import data.gateway.authz
import rego.v1

test_allow_tools_list if {
	authz.allow with input as {"method": "tools/list", "tool_name": "", "bare_tool_name": "", "target": null}
}

test_allow_search_documentation if {
	authz.allow with input as {
		"method": "tools/call",
		"tool_name": "mac-akto-api-mcp___searchDocumentation",
		"bare_tool_name": "searchDocumentation",
		"target": "mac-akto-api-mcp",
	}
}

test_allow_get_page if {
	authz.allow with input as {
		"method": "tools/call",
		"tool_name": "mac-akto-ai-mcp___getPage",
		"bare_tool_name": "getPage",
		"target": "mac-akto-ai-mcp",
	}
}

# sendFeedback is intentionally allowed by OPA -- blocking moved to the
# Approval Agent (APPROVAL_REQUIRED, not an OPA BLOCK). See main.rego.
test_allow_send_feedback_api_target if {
	authz.allow with input as {
		"method": "tools/call",
		"tool_name": "mac-akto-api-mcp___sendFeedback",
		"bare_tool_name": "sendFeedback",
		"target": "mac-akto-api-mcp",
	}
}

test_allow_send_feedback_ai_target if {
	authz.allow with input as {
		"method": "tools/call",
		"tool_name": "mac-akto-ai-mcp___sendFeedback",
		"bare_tool_name": "sendFeedback",
		"target": "mac-akto-ai-mcp",
	}
}

test_block_reason_empty_when_allowed if {
	authz.block_reason == "" with input as {
		"method": "tools/call",
		"tool_name": "mac-akto-api-mcp___sendFeedback",
		"bare_tool_name": "sendFeedback",
		"target": "mac-akto-api-mcp",
	}
}
