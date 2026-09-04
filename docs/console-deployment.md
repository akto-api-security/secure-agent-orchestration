# Deploying from the AWS Console

Click-by-click build of the same topology Terraform creates:

```text
Client → HTTP Gateway → AgentCore Runtime → MCP Gateway → Akto docs tools
```

Everything below uses region **us-east-1** and the default names from
`infra/environments/akto-demo`. Replace `<ACCOUNT_ID>` with your account id
throughout.

Two things genuinely cannot be done in the console, and both are called out
where they occur:

- **Building and pushing the container image.** There is no console image
builder; you need Docker locally (step 2) or a CodeBuild project.
- **Invoking the agent.** AgentCore Gateways have no console "test" button,
so verification in step 9 uses the AWS CLI.

Console labels shift between AWS releases. Where a label may differ, the
underlying API field name is given in parentheses.

## Resource inventory

Build in this order; each step needs an ARN from the previous one.


| #   | Resource                                | Name                                         |
| --- | --------------------------------------- | -------------------------------------------- |
| 1   | Bedrock model access                    | Claude Haiku 4.5                             |
| 2   | ECR repository + image                  | `asl-demo-agent-demo`                        |
| 3   | MCP Gateway role                        | `asl-gateway-service-role-demo`              |
| 4   | MCP Gateway + 2 targets                 | `asl-gateway-demo`                           |
| 5   | Runtime execution role                  | `asl-demo-agent-execution-demo`              |
| 6   | AgentCore Runtime                       | `asl_demo_agent_demo`                        |
| 7   | HTTP Gateway role                       | `asl-http-gateway-demo`                      |
| 8   | HTTP Gateway + Runtime target           | `asl-http-gateway-demo`, target `demo-agent` |
| 9   | Runtime resource policy + caller policy | `asl-http-gateway-invoke-demo`               |




## 1. Enable the Bedrock model

**Amazon Bedrock** → **Model access** → **Modify model access**. Enable
**Anthropic Claude Haiku 4.5** and submit. The agent uses inference profile
`us.anthropic.claude-haiku-4-5-20251001-v1:0`.

## 2. ECR repository and image

**Amazon ECR** → **Repositories** → **Create repository**.

- Visibility: **Private**
- Name: `asl-demo-agent-demo`
- Tag immutability: **Immutable**
- Scan on push: **Enabled**

Open the repository → **View push commands**, then build for **arm64**
(AgentCore Runtime is Graviton). Run locally, from the repo root:

```bash
export AWS_REGION=us-east-1
export ACCOUNT_ID=<ACCOUNT_ID>
export REPO_URL="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/asl-demo-agent-demo"
export IMAGE_TAG="build-$(date -u +%Y%m%d%H%M%S)"

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

docker buildx build --platform linux/arm64 \
  -t "${REPO_URL}:${IMAGE_TAG}" --push agents/akto-demo-agent
```

Because the repository is immutable, every deploy needs a new tag. Copy the
full `…:${IMAGE_TAG}` URI; step 6 needs it.

## 3. MCP Gateway service role

**IAM** → **Roles** → **Create role** → **Custom trust policy**:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GatewayAssumeRolePolicy",
      "Effect": "Allow",
      "Principal": { "Service": "bedrock-agentcore.amazonaws.com" },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": { "aws:SourceAccount": "<ACCOUNT_ID>" }
      }
    }
  ]
}
```

Skip permissions for now, name it `asl-gateway-service-role-demo`, create.

Open the role → **Add permissions** → **Create inline policy** → **JSON**,
name `asl-gateway-logs-demo`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:us-east-1:<ACCOUNT_ID>:log-group:/aws/bedrock-agentcore/gateways/*"
    }
  ]
}
```

Both Akto documentation MCP servers are public and need no outbound
auth, so this role needs nothing else.

## 4. MCP Gateway and its two targets

**Bedrock AgentCore** → **Gateways** → **Create gateway**.

- Name: `asl-gateway-demo`
- Protocol (`protocolType`): **MCP**
- Inbound authorization (`authorizerType`): **AWS IAM**
- Service role (`roleArn`): `asl-gateway-service-role-demo`

Create it, then add two targets on the gateway's **Targets** tab.

Target 1:

- Name: `mac-akto-api-mcp`
- Type (`targetConfiguration`): **MCP server** (remote/streamable HTTP)
- Endpoint: `https://docs.akto.io/~gitbook/mcp`
- Outbound auth: **None**

Target 2:

- Name: `mac-akto-ai-mcp`
- Type: **MCP server**
- Endpoint: `https://ai-security-docs.akto.io/~gitbook/mcp`
- Outbound auth: **None**

Record the gateway **ARN** and **MCP URL**. The URL looks like:

```text
https://asl-gateway-demo-<suffix>.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp
```



## 5. Runtime execution role

**IAM** → **Create role** → **Custom trust policy**:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeRolePolicy",
      "Effect": "Allow",
      "Principal": { "Service": "bedrock-agentcore.amazonaws.com" },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": { "aws:SourceAccount": "<ACCOUNT_ID>" },
        "ArnLike": {
          "aws:SourceArn": "arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:*"
        }
      }
    }
  ]
}
```

Name it `asl-demo-agent-execution-demo`, then attach an inline policy named
`asl-demo-agent-execution-demo`. Replace `<MCP_GATEWAY_ARN>` with the ARN
from step 4:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRImageAccess",
      "Effect": "Allow",
      "Action": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
      "Resource": "arn:aws:ecr:us-east-1:<ACCOUNT_ID>:repository/asl-demo-agent-demo"
    },
    {
      "Sid": "ECRTokenAccess",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "LogGroupCreation",
      "Effect": "Allow",
      "Action": ["logs:DescribeLogStreams", "logs:CreateLogGroup"],
      "Resource": "arn:aws:logs:us-east-1:<ACCOUNT_ID>:log-group:/aws/bedrock-agentcore/runtimes/*"
    },
    {
      "Sid": "LogGroupPolicy",
      "Effect": "Allow",
      "Action": "logs:PutResourcePolicy",
      "Resource": "arn:aws:logs:us-east-1:<ACCOUNT_ID>:log-group:/aws/bedrock-agentcore/runtimes/asl_demo_agent_demo-*"
    },
    {
      "Sid": "LogGroupDescribe",
      "Effect": "Allow",
      "Action": "logs:DescribeLogGroups",
      "Resource": "arn:aws:logs:us-east-1:<ACCOUNT_ID>:log-group:*"
    },
    {
      "Sid": "LogStreamWrite",
      "Effect": "Allow",
      "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:us-east-1:<ACCOUNT_ID>:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
    },
    {
      "Sid": "Tracing",
      "Effect": "Allow",
      "Action": [
        "xray:PutTraceSegments",
        "xray:PutTelemetryRecords",
        "xray:GetSamplingRules",
        "xray:GetSamplingTargets"
      ],
      "Resource": "*"
    },
    {
      "Sid": "Metrics",
      "Effect": "Allow",
      "Action": "cloudwatch:PutMetricData",
      "Resource": "*",
      "Condition": {
        "StringEquals": { "cloudwatch:namespace": "bedrock-agentcore" }
      }
    },
    {
      "Sid": "GetAgentAccessToken",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:GetWorkloadAccessToken",
        "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
        "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
      ],
      "Resource": [
        "arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:workload-identity-directory/default",
        "arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:workload-identity-directory/default/workload-identity/asl_demo_agent_demo-*"
      ]
    },
    {
      "Sid": "BedrockModelInvocation",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": [
        "arn:aws:bedrock:*::foundation-model/*",
        "arn:aws:bedrock:us-east-1:<ACCOUNT_ID>:*"
      ]
    },
    {
      "Sid": "InvokeGateway",
      "Effect": "Allow",
      "Action": "bedrock-agentcore:InvokeGateway",
      "Resource": "<MCP_GATEWAY_ARN>"
    }
  ]
}
```



## 6. AgentCore Runtime

**Bedrock AgentCore** → **Agent Runtimes** → **Host agent** / **Create**.

- Name (`agentRuntimeName`): `asl_demo_agent_demo` — letters, digits, and
underscores only; hyphens are rejected
- Artifact: **Container image**, URI `…/asl-demo-agent-demo:<IMAGE_TAG>`
- Execution role: `asl-demo-agent-execution-demo`
- Inbound protocol (`serverProtocol`): **HTTP**
- Inbound authorization: **AWS IAM** (leave any JWT/OAuth authorizer empty)
- Network mode: **Public**
- Description: anything, e.g. "Demo agent behind an HTTP Gateway"

Environment variables:


| Key                 | Value                                         |
| ------------------- | --------------------------------------------- |
| `GATEWAY_URL`       | MCP URL from step 4 (ends in `/mcp`)          |
| `GATEWAY_REGION`    | `us-east-1`                                   |
| `MCP_TARGET_PREFIX` | `mac-akto-api-mcp`                            |
| `BEDROCK_MODEL_ID`  | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |


Create it and copy the **Runtime ARN**.

## 7. HTTP Gateway service role

**IAM** → **Create role** → **Custom trust policy**. The `SourceArn`
wildcard matches the gateway created in step 8, so this role cannot be used
by any other gateway:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "bedrock-agentcore.amazonaws.com" },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": { "aws:SourceAccount": "<ACCOUNT_ID>" },
        "ArnLike": {
          "aws:SourceArn": "arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:gateway/asl-http-gateway-demo-*"
        }
      }
    }
  ]
}
```

Name it `asl-http-gateway-demo`, then add an inline policy of the same name.
Replace `<RUNTIME_ARN>` with the ARN from step 6:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeRuntime",
      "Effect": "Allow",
      "Action": "bedrock-agentcore:InvokeAgentRuntime",
      "Resource": ["<RUNTIME_ARN>", "<RUNTIME_ARN>/*"]
    },
    {
      "Sid": "WriteGatewayLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:us-east-1:<ACCOUNT_ID>:log-group:/aws/bedrock-agentcore/gateways/*"
    }
  ]
}
```



## 8. HTTP Gateway and the Runtime target

**Bedrock AgentCore** → **Gateways** → **Create gateway**.

- Name: `asl-http-gateway-demo`
- Protocol: **leave unset / none**. This is the important one — a gateway
created with `protocolType=MCP` rejects HTTP targets, and you cannot
change it afterwards. If the console forces a choice, pick the
non-MCP/HTTP option.
- Inbound authorization: **AWS IAM**
- Service role: `asl-http-gateway-demo`

Add one target:

- Name: `demo-agent` — this becomes the URL path segment
- Type: **HTTP** → **AgentCore Runtime**
- Runtime ARN: from step 6
- Qualifier: `DEFAULT`
- Outbound credentials (`credentialProviderConfiguration`): **Gateway IAM
role**
- Response mode: **buffered**, not streaming. Streaming responses bypass
interceptors, so Akto could not scan them later.

Record the gateway ARN and URL. Invocations go to:

```text
https://asl-http-gateway-demo-<suffix>.gateway.bedrock-agentcore.us-east-1.amazonaws.com/demo-agent/invocations
```



## 9. Lock the Runtime, then allow the caller

Two policies. The first is what makes the guardrail path
non-bypassable; without it, anyone holding `InvokeAgentRuntime` can skip
the gateway.

**9a. Runtime resource policy.** The console does not expose resource
policies for AgentCore Runtimes, so use the CLI. Replace both placeholders,
then:

```bash
cat > /tmp/runtime-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOnlyHttpGateway",
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::<ACCOUNT_ID>:role/asl-http-gateway-demo" },
      "Action": "bedrock-agentcore:InvokeAgentRuntime",
      "Resource": "<RUNTIME_ARN>"
    },
    {
      "Sid": "DenyDirectInvocation",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "bedrock-agentcore:InvokeAgentRuntime",
      "Resource": "<RUNTIME_ARN>",
      "Condition": {
        "ArnNotEquals": {
          "aws:PrincipalArn": "arn:aws:iam::<ACCOUNT_ID>:role/asl-http-gateway-demo"
        }
      }
    }
  ]
}
EOF

aws bedrock-agentcore-control put-resource-policy \
  --resource-arn "<RUNTIME_ARN>" \
  --policy "file:///tmp/runtime-policy.json" \
  --region us-east-1
```

**9b. Caller policy.** **IAM** → **Policies** → **Create policy** → **JSON**,
named `asl-http-gateway-invoke-demo`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeHttpGateway",
      "Effect": "Allow",
      "Action": "bedrock-agentcore:InvokeGateway",
      "Resource": "<HTTP_GATEWAY_ARN>"
    }
  ]
}
```

Attach it to the user or role that will call the agent.

## 10. Verify

No console invoke exists for gateways, so use the CLI. Allowed path:

```bash
export HTTP_GATEWAY_URL="https://asl-http-gateway-demo-<suffix>.gateway.bedrock-agentcore.us-east-1.amazonaws.com"
export AGENT_RUNTIME_ARN="<RUNTIME_ARN>"

echo '{"prompt":"What does API security testing cover in Akto?"}' > /tmp/payload.json

aws bedrock-agentcore invoke-agent-runtime \
  --endpoint-url "${HTTP_GATEWAY_URL}/demo-agent" \
  --agent-runtime-arn "${AGENT_RUNTIME_ARN}" \
  --qualifier DEFAULT \
  --payload fileb:///tmp/payload.json \
  --region us-east-1 \
  /tmp/response.json

python3 -m json.tool /tmp/response.json
```

Expect `"status": "success"` and an answer citing Akto docs, which proves
the MCP hop worked too.

Bypass must fail with an explicit deny from step 9a:

```bash
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "${AGENT_RUNTIME_ARN}" \
  --payload fileb:///dev/stdin \
  --region us-east-1 /tmp/bypass.json <<< '{"prompt":"hi"}'
```

Runtime logs live in CloudWatch under
`/aws/bedrock-agentcore/runtimes/asl_demo_agent_demo-*`.

## 11. Attach Akto (optional)

Both gateway IDs are on their console detail pages. Follow the
[AgentCore connector guide](https://ai-security-docs.akto.io/akto-argus-agentic-ai-security-for-homegrown-ai/connectors/ai-agent-security/aws-bedrock-agentcore),
which has its own **Deploy from AWS Console** tab: create the interceptor
Lambda, attach the Akto layer, set `AKTO_DATA_INGESTION_URL` and
`AKTO_API_TOKEN`, grant each gateway role `lambda:InvokeFunction`, then set
the same function ARN as both REQUEST and RESPONSE interceptor on **both**
gateways with pass-request-headers on and the response body included.

## 12. Delete

Reverse order, because targets and roles are referenced:

1. Gateway targets, then both gateways
2. AgentCore Runtime
3. Interceptor Lambda, if created
4. ECR repository (delete images first, or use **Delete** with force)
5. IAM roles `asl-gateway-service-role-demo`,
  `asl-demo-agent-execution-demo`, `asl-http-gateway-demo`, and policy
   `asl-http-gateway-invoke-demo`
6. CloudWatch log groups under `/aws/bedrock-agentcore/`

Console-created resources are invisible to Terraform. Do not run
`scripts/destroy.sh` against them; it only knows about state in S3.