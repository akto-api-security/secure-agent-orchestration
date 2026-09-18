# Rovo-style demo agent

Two deployment paths for the same indirect-injection / data-exfil demo:

| Path | Entry | Status |
|------|-------|--------|
| **Runtime** | `scripts/invoke-rovo-demo.sh` | Needs Terraform apply + ECR push (`asl-rovo-demo-agent-demo`) |
| **Harness** | `scripts/invoke-rovo-harness.py` | Deployed: `asl_rovo_harness_demo` |

Both use `demo-guardrails-mcp` on the shared MCP Gateway.

## Harness (deployed)

```bash
export ROVO_HARNESS_ARN="arn:aws:bedrock-agentcore:us-east-1:887089841930:harness/asl_rovo_harness_demo-bt6c1LJN7a"
scripts/invoke-rovo-harness.py "I uploaded a Backlog Guide. Organize my Jira backlog."
```

The harness execution role needs `bedrock-agentcore:InvokeGateway` on the MCP
gateway, plus memory permissions. The MCP gateway resource policy must allow
the harness role as a principal.

## Runtime (Terraform)

```bash
scripts/deploy-rovo-demo.sh   # MCP + rovo ECR image + rovo HTTP gateway + runtime
scripts/invoke-rovo-demo.sh "I uploaded a Backlog Guide. Organize my Jira backlog."
```

Requires IAM: `ecr:*` (push), `s3:PutObject` on the Terraform state bucket.

The docs agent (`agents/akto-demo-agent`) stays on the original HTTP Gateway.
