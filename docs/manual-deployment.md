# Manual deployment

This is the same topology the scripts deploy, written as copy-paste
commands. The shortcuts are:

```bash
scripts/check_prereqs.sh
scripts/bootstrap.sh us-east-1 agentcore-gateway-demo
scripts/deploy.sh
scripts/invoke.sh "What does API security testing cover in Akto?"
scripts/destroy.sh
```

What gets created:

```text
Client → HTTP Gateway → AgentCore Runtime → MCP Gateway → Akto docs tools
```

The Runtime resource policy allows invocation only from the HTTP Gateway
role. Do not invoke the Runtime ARN directly.

Akto interceptors are **not** created here. Attach them after the AWS
topology is up, using the
[AgentCore connector guide](https://ai-security-docs.akto.io/akto-argus-agentic-ai-security-for-homegrown-ai/connectors/ai-agent-security/aws-bedrock-agentcore).

## 0. Prerequisites

- AWS CLI v2, authenticated (`aws sts get-caller-identity` succeeds)
- Terraform 1.10 or newer
- Python 3
- Bedrock model access for `us.anthropic.claude-haiku-4-5-20251001-v1:0`
- A region that supports AgentCore Runtime and Gateway (`us-east-1` below)
- **Option A (ECR / Terraform Runtime):** Docker with `buildx`
- **Option B (zip):** none. Use
  `agents/akto-demo-agent/deployment_package.zip` in this repo.

This environment's Terraform Runtime is **container-only**. `scripts/deploy.sh`
and the `terraform apply` in step 5 need Option A. Use Option B when you
create the Runtime from that zip (console Host Agent local upload, or CLI
`codeConfiguration`). The zip is account-independent; IAM, gateway URL, and
model access are per account.

```bash
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION=us-east-1
aws sts get-caller-identity
terraform version
docker buildx version   # Option A only
```

Optional names used throughout. Change them consistently if you fork the
defaults:

```bash
export PROJECT_NAME=agentcore-gateway-demo
export ENVIRONMENT=demo
export ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export IMAGE_TAG="build-$(date -u +%Y%m%d%H%M%S)"
export CODE_BUCKET="asl-demo-agent-code-${ACCOUNT_ID}-${AWS_REGION}"
export ZIP_KEY="asl-demo-agent-demo/deployment_package.zip"
```

For Option A the ECR repository is **immutable**. Always use a new
`IMAGE_TAG`. Do not use `latest`.

From the repository root:

```bash
cd /path/to/secure-agent-orchestration
```

## 1. Terraform state bucket

This step is `scripts/bootstrap.sh`. It creates an S3 bucket named
`${PROJECT_NAME}-tfstate-${ACCOUNT_ID}` (versioned, KMS, public access
blocked). Bootstrap state stays **local** under `infra/bootstrap/` and is
gitignored.

```bash
cd infra/bootstrap
terraform init
terraform apply \
  -var="aws_region=${AWS_REGION}" \
  -var="project_name=${PROJECT_NAME}"
export STATE_BUCKET="$(terraform output -raw state_bucket_name)"
cd ../..
```

Write the gitignored backend file the environment uses at `terraform init`:

```bash
cat > infra/environments/akto-demo/backend.hcl <<EOF
bucket = "${STATE_BUCKET}"
region = "${AWS_REGION}"
EOF
```

The environment backend key is fixed in `backend.tf` as
`agentcore-demo/terraform.tfstate`.

## 2. Optional Terraform variables

Defaults already match the values above. To override:

```bash
cp infra/environments/akto-demo/terraform.tfvars.example \
   infra/environments/akto-demo/terraform.tfvars
```

Edit `aws_region`, `project_name`, `environment`, and `http_target_name` if
needed. `http_target_name` becomes the path segment on the HTTP Gateway
(default `demo-agent`).

## 3. Initialize the environment

```bash
cd infra/environments/akto-demo
terraform init -backend-config=backend.hcl
```

If you already initialized this directory against another backend, add
`-reconfigure`.

## 4. Runtime artifact (ECR image **or** zip)

Pick one. Step 5 Terraform needs Option A.

### Option A — ECR container (Terraform)

The Runtime cannot be created until the image exists. Create only the
repository first (this is the `-target` apply in `scripts/deploy.sh`):

```bash
terraform apply \
  -var="image_tag=${IMAGE_TAG}" \
  -var="aws_region=${AWS_REGION}" \
  -target=module.demo_agent.aws_ecr_repository.this
```

```bash
export REPO_URL="$(terraform output -raw demo_agent_ecr_repository_url)"
export REGISTRY="${REPO_URL%%/*}"
```

Build and push `linux/arm64` (AgentCore Runtime on Graviton):

```bash
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${REGISTRY}"

docker buildx build \
  --platform linux/arm64 \
  -t "${REPO_URL}:${IMAGE_TAG}" \
  --push \
  ../../../agents/akto-demo-agent
```

The Dockerfile is already `FROM --platform=linux/arm64 python:3.12-slim`.
Continue at step 5.

### Option B — Zip (direct code deploy)

Use the zip in this repo. Do not rebuild it unless you changed agent code:

```text
agents/akto-demo-agent/deployment_package.zip
```

Linux arm64, Python 3.12, `main.py` at the zip root, account-independent.

**Console:** **Host agent** → **Local upload** that file. Runtime
**Python 3.12**, entry point `main.py`. Click-path:
[docs/console-deployment.md](console-deployment.md) step 6.

**CLI `create-agent-runtime`** cannot take a local file. Optional: upload
the same zip to S3 (`us-east-1` omits `LocationConstraint`):

```bash
aws s3api create-bucket --bucket "${CODE_BUCKET}" --region "${AWS_REGION}"

aws s3api put-public-access-block \
  --bucket "${CODE_BUCKET}" \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws s3 cp agents/akto-demo-agent/deployment_package.zip \
  "s3://${CODE_BUCKET}/${ZIP_KEY}" \
  --region "${AWS_REGION}"
```

The execution role and the caller of `create-agent-runtime` both need
`s3:GetObject` on that object. After the MCP Gateway exists (step 5's
gateway, or create it first with
`-target=module.mcp_gateway`):

```bash
export MCP_GATEWAY_URL="$(terraform -chdir=infra/environments/akto-demo output -raw mcp_gateway_url)"
export EXEC_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/asl-demo-agent-execution-${ENVIRONMENT}"

aws iam put-role-policy \
  --role-name "asl-demo-agent-execution-${ENVIRONMENT}" \
  --policy-name S3CodeAccess \
  --policy "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{
      \"Effect\": \"Allow\",
      \"Action\": [\"s3:GetObject\", \"s3:GetObjectVersion\"],
      \"Resource\": \"arn:aws:s3:::${CODE_BUCKET}/${ZIP_KEY}\"
    }]
  }"

aws bedrock-agentcore-control create-agent-runtime \
  --region "${AWS_REGION}" \
  --agent-runtime-name "asl_demo_agent_${ENVIRONMENT}" \
  --role-arn "${EXEC_ROLE_ARN}" \
  --description "Demo agent from zip" \
  --network-configuration '{"networkMode":"PUBLIC"}' \
  --protocol-configuration '{"serverProtocol":"HTTP"}' \
  --environment-variables "{
    \"GATEWAY_URL\": \"${MCP_GATEWAY_URL}\",
    \"GATEWAY_REGION\": \"${AWS_REGION}\",
    \"MCP_TARGET_PREFIX\": \"mac-akto-api-mcp\",
    \"BEDROCK_MODEL_ID\": \"us.anthropic.claude-haiku-4-5-20251001-v1:0\"
  }" \
  --agent-runtime-artifact "{
    \"codeConfiguration\": {
      \"code\": {
        \"s3\": {
          \"bucket\": \"${CODE_BUCKET}\",
          \"prefix\": \"${ZIP_KEY}\"
        }
      },
      \"runtime\": \"PYTHON_3_12\",
      \"entryPoint\": [\"main.py\"]
    }
  }"
```

Do not also `terraform apply` `module.demo_agent`'s Runtime against the
same name: that resource always points at ECR. For a zip-backed Runtime,
create the HTTP Gateway and resource policy with the CLI/console steps in
[docs/console-deployment.md](console-deployment.md) (steps 7–9), using the
ARN printed by `create-agent-runtime`.

Optional — rebuild the zip only if you changed `agents/akto-demo-agent/`:

```bash
rm -rf /tmp/agentcore-zip && mkdir -p /tmp/agentcore-zip
uv pip install \
  --python-platform aarch64-manylinux2014 \
  --python-version 3.12 \
  --target=/tmp/agentcore-zip \
  --only-binary=:all: \
  -r agents/akto-demo-agent/requirements.txt
cp agents/akto-demo-agent/main.py agents/akto-demo-agent/gateway_tool.py \
  /tmp/agentcore-zip/
( cd /tmp/agentcore-zip && zip -qr /tmp/deployment_package.zip . )
cp /tmp/deployment_package.zip agents/akto-demo-agent/deployment_package.zip
```

## 5. Deploy the rest of the topology (Option A)

Option A only. Still in `infra/environments/akto-demo`:

```bash
terraform apply \
  -var="image_tag=${IMAGE_TAG}" \
  -var="aws_region=${AWS_REGION}"
```

This creates, in order of dependencies:

1. MCP Gateway (IAM auth) and two MCP targets:
   - `mac-akto-api-mcp` → `https://docs.akto.io/~gitbook/mcp`
   - `mac-akto-ai-mcp` → `https://ai-security-docs.akto.io/~gitbook/mcp`
2. AgentCore Runtime (HTTP) using `${REPO_URL}:${IMAGE_TAG}`
3. HTTP Gateway (IAM auth, no MCP protocol type) with an
   `http.agentcoreRuntime` target named `demo-agent`
4. Runtime resource policy that denies anyone except the HTTP Gateway role

Print the outputs:

```bash
terraform output
```

Useful values:

```bash
terraform output -raw http_gateway_id
terraform output -raw http_gateway_url
terraform output -raw http_gateway_target_name
terraform output -raw http_gateway_invoke_policy_arn
terraform output -raw demo_agent_runtime_arn
terraform output -raw mcp_gateway_id
terraform output -raw mcp_gateway_url
```

Attach `http_gateway_invoke_policy_arn` to the IAM identity that will call
the agent (`bedrock-agentcore:InvokeGateway`). Your current principal needs
that permission to run the invoke steps below.

## 6. Invoke

Always use the **HTTP Gateway**. From the repository root:

```bash
cd /path/to/secure-agent-orchestration

export HTTP_GATEWAY_URL="$(terraform -chdir=infra/environments/akto-demo output -raw http_gateway_url)"
export HTTP_GATEWAY_TARGET="$(terraform -chdir=infra/environments/akto-demo output -raw http_gateway_target_name)"
export AGENT_RUNTIME_ARN="$(terraform -chdir=infra/environments/akto-demo output -raw demo_agent_runtime_arn)"
export MCP_GATEWAY_URL="$(terraform -chdir=infra/environments/akto-demo output -raw mcp_gateway_url)"
```

Agent through the HTTP Gateway (`scripts/invoke.sh`):

```bash
python3 -c 'import json,sys; json.dump({"prompt": sys.argv[1]}, sys.stdout)' \
  "What does API security testing cover in Akto?" > /tmp/agent-payload.json

aws bedrock-agentcore invoke-agent-runtime \
  --endpoint-url "${HTTP_GATEWAY_URL%/}/${HTTP_GATEWAY_TARGET}" \
  --agent-runtime-arn "${AGENT_RUNTIME_ARN}" \
  --qualifier DEFAULT \
  --payload fileb:///tmp/agent-payload.json \
  --region "${AWS_REGION}" \
  /tmp/agent-response.json

python3 -m json.tool /tmp/agent-response.json
```

Expected: `"status": "success"` and an answer grounded in Akto docs.

Direct MCP call, bypassing the agent (`scripts/mcp-call.py`):

```bash
scripts/mcp-call.py list
scripts/mcp-call.py call searchDocumentation '{"query":"BOLA"}'
```

Direct Runtime invoke **must fail** with an explicit deny:

```bash
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "${AGENT_RUNTIME_ARN}" \
  --payload fileb:///dev/stdin \
  --region "${AWS_REGION}" \
  /tmp/bypass-out.json <<< '{"prompt":"hi"}'
```

## 7. Attach Akto (optional, after topology)

Not Terraform. Use the two Gateway IDs:

```bash
terraform -chdir=infra/environments/akto-demo output -raw http_gateway_id
terraform -chdir=infra/environments/akto-demo output -raw mcp_gateway_id
```

Follow the
[AgentCore connector guide](https://ai-security-docs.akto.io/akto-argus-agentic-ai-security-for-homegrown-ai/connectors/ai-agent-security/aws-bedrock-agentcore):

- Clone `https://github.com/akto-api-security/aws-bedrock-agentcore.git`
- Set `AKTO_DATA_INGESTION_URL`, `AKTO_API_TOKEN`, `AKTO_LAYER_ARN`,
  `AWS_REGION`, and `GATEWAY_IDS` (both IDs, comma-separated)
- Run `deploy/deploy.sh` **only if those gateways have no interceptor yet**

Attach REQUEST and RESPONSE on **both** gateways, pass request headers on,
response body included. Then re-run the invoke commands in step 6.

## 8. Destroy

This is `scripts/destroy.sh` for Option A. ECR must be emptied first
because images block repository delete. The state **bucket is left in
place**.

```bash
cd /path/to/secure-agent-orchestration/infra/environments/akto-demo
REPO_URL="$(terraform output -raw demo_agent_ecr_repository_url)"
aws ecr delete-repository \
  --repository-name "${REPO_URL##*/}" \
  --region "${AWS_REGION}" \
  --force
terraform destroy
```

Option B: delete the Runtime in the console or with
`aws bedrock-agentcore-control delete-agent-runtime`, then remove the zip:

```bash
aws s3 rm "s3://${CODE_BUCKET}/${ZIP_KEY}" --region "${AWS_REGION}"
aws s3api delete-bucket --bucket "${CODE_BUCKET}" --region "${AWS_REGION}"
```

To also remove the state bucket (not done by the script):

```bash
cd ../../bootstrap
terraform destroy
```

That deletes versioned objects only if the bucket is empty or you empty it
first; you may need to delete object versions in the console before destroy
succeeds.
