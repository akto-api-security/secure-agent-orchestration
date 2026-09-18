#!/usr/bin/env bash
# Deploy demo guardrails MCP server and register it on the MCP Gateway.
# Usage: scripts/deploy-demo-mcp.sh [image-tag]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"${SCRIPT_DIR}/deploy-demo-mcp-server.sh" "${1:-latest}"
"${SCRIPT_DIR}/register-demo-mcp-target.sh"
