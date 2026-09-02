# Demo agent

This HTTP AgentCore Runtime receives `{"prompt":"..."}`, discovers tools from
the inner MCP Gateway, and answers from Akto documentation.

Deploy and invoke it only through the outer HTTP Gateway:

```bash
scripts/deploy.sh
scripts/invoke.sh "What does API security testing cover in Akto?"
```

The Runtime resource policy rejects direct invocation.
