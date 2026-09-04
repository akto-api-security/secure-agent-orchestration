# Demo agent

This HTTP AgentCore Runtime receives `{"prompt":"..."}`, discovers tools from
the inner MCP Gateway, and answers from Akto documentation.

Deploy and invoke it only through the outer HTTP Gateway:

```bash
scripts/deploy.sh
scripts/invoke.sh "What does API security testing cover in Akto?"
```

The Runtime resource policy rejects direct invocation.

For console Host Agent, upload
`agents/akto-demo-agent/deployment_package.zip` directly (Local upload,
Python 3.12, entry point `main.py`). Rebuild it only if you change this
agent.
