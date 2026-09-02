# Deployment environment

This Terraform root deploys:

```text
Client -> HTTP Gateway -> Runtime -> MCP Gateway -> tools
```

It creates no interceptor. Install Akto after the topology is running by
following the connector guide linked from the repository README.

Use the repository scripts from the project root:

```bash
scripts/bootstrap.sh
scripts/deploy.sh
scripts/invoke.sh "What does API security testing cover?"
scripts/smoke-test.sh
```

Useful outputs:

```bash
terraform -chdir=infra/environments/akto-demo output
```

The outer Gateway uses AWS IAM authorization. Its target uses the Gateway
service role to invoke the Runtime. A Runtime resource policy accepts that
role and rejects direct invocation paths.
