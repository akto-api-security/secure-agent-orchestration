# Agent Security Lab

Standalone AWS replica of a client's existing Amazon Bedrock AgentCore security
architecture, used to prototype and test security controls without touching
the client's environment.

**Akto integration (Guardrail, SDK, dashboard, enforcement layer) is explicitly
out of scope until a later phase.** This repo currently contains no Akto
components.

## Architecture (locked)

```
User
  |
  v
Orchestrator Agent
  | A2A
  +--------------------------------+
  |                                |
  v                                v
API Security Agent          Agentic Security Agent
(AgentCore Runtime)         (AgentCore Runtime)
  |                                |
  +--------------------------------+
                 |
                 v
        AgentCore Gateway
                 |
                 v
      REQUEST Interceptor Lambda  <---- verifies signed grants on resume
                 |
                 v
        OPA policy enforcement (baseline layer)
                 |
                 v
           Approval Agent (AgentCore Runtime)
        - deterministic approval (e.g. sendFeedback)
        - semantic HITL (e.g. DAST-related requests, real LLM call)
        - signed authorization grants (AWS KMS)
        - human decision state (DynamoDB)
                 |
                 v
     Human: approve / deny / additional instruction
                 |
                 v
      Existing remote MCP servers (only on ALLOW)
       - mac-akto-api-mcp
       - mac-akto-ai-mcp
```

The Approval Agent owns all approval/HITL decision-making; the interceptor
only routes to it and enforces the result. A human decides via the demo UI
(`ui/`) or a CLI script; an approved request resumes with a signed,
single-use grant (KMS) that the interceptor verifies before allowing
execution.

## Repository layout

| Path | Purpose |
|---|---|
| `infra/` | Terraform: state backend (`infra/bootstrap`) + the deployable stack (`infra/environments/dev`) -- Gateway, delegated agents, Orchestrator, interceptor, Approval Agent |
| `agents/orchestrator/` | Orchestrator Agent -- independently buildable (own `Dockerfile`/`requirements.txt`) |
| `agents/api-security-agent/` | API Security Agent -- independently buildable |
| `agents/agentic-security-agent/` | Agentic Security Agent -- independently buildable |
| `approval-agent/` | Approval Agent -- deterministic + semantic (LLM) approval rules, signed grants, human decision state -- independently buildable |
| `interceptor/` | REQUEST interceptor Lambda + OPA baseline policy; routes approval decisions to the Approval Agent |
| `ui/` | Lightweight demo UI -- FastAPI backend + static HTML/JS, calls only the Orchestrator and Approval Agent runtimes |
| `scripts/` | Deployment/build/verify scripts used in the steps below |

Every service under `agents/` and `approval-agent/` is independently
buildable and deployable -- the Gateway, interceptor, OPA policy, and
Terraform are managed as separate infrastructure, not bundled into any one
service.

## Prerequisites

Before you start, make sure you have:

1. **An AWS account** with an authenticated CLI identity
   (`aws sts get-caller-identity` succeeds) that has permission to create:
   Bedrock AgentCore resources, ECR repositories, a Lambda function, a
   DynamoDB table, a KMS key, IAM roles/policies, an S3 bucket, and
   CloudWatch Logs. This is a lab/demo project -- broad (e.g. admin-level)
   permissions on a non-production account are the simplest way to avoid
   chasing individual missing permissions.
2. **Bedrock model access enabled** in your target region for the model
   this project uses by default
   (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) -- check the Bedrock
   console's "Model access" page, or confirm from the CLI:
   ```bash
   aws bedrock list-inference-profiles --region us-east-1 \
     --query "inferenceProfileSummaries[?inferenceProfileId=='us.anthropic.claude-haiku-4-5-20251001-v1:0']"
   ```
   An empty result means you need to request access in the console first --
   Terraform will deploy successfully either way, but every agent invoke
   will fail at runtime without this.
3. **A region with full Bedrock AgentCore support.** `us-east-1` is used
   throughout this project and is confirmed to have it; if you pick a
   different region, confirm AgentCore Runtime/Gateway are available there
   first.
4. **Terraform >= 1.10**
5. **Docker** with `buildx` (bundled with Docker Desktop) -- all 4 images
   are built for `linux/arm64` (a hard AgentCore requirement), which builds
   natively on Apple Silicon and via Docker Desktop's bundled QEMU
   emulation on Intel/AMD64 hosts (just slower).
6. **Python 3.10+** (3.13 recommended, to match the interceptor Lambda's
   runtime) -- used for the demo UI and local script/test runs, not for
   anything deployed to AWS.

Run `scripts/check_prereqs.sh` to verify the AWS CLI, Terraform, and Python
are all present and that your AWS credentials are valid. It does not check
Docker or Bedrock model access -- confirm those yourself per the steps
above.

## Running this from scratch

These steps take you from a fresh clone to a fully deployed stack with a
working demo. Every command below is safe to run from the repository root
unless noted otherwise.

### Step 1 -- Clone the repository

```bash
git clone <this-repo-url>
cd secure-agent-orchestration
```

### Step 2 -- Configure AWS credentials

```bash
aws configure          # or `aws sso login` if your org uses SSO
aws sts get-caller-identity   # confirms your credentials work
```

### Step 3 -- Verify prerequisites

```bash
bash scripts/check_prereqs.sh
```

Fix anything it flags before continuing.

### Step 4 -- Bootstrap the Terraform state backend

Creates the one S3 bucket that will hold this deployment's Terraform state.

```bash
scripts/bootstrap.sh <region> <project_name>   # e.g. scripts/bootstrap.sh us-east-1 agent-security-lab
```

This asks for confirmation before touching AWS, then writes
`infra/environments/dev/backend.hcl` (gitignored, account-specific) for you.
If you'd rather do it by hand, see `infra/bootstrap/` and
`infra/environments/dev/backend.hcl.example`.

### Step 5 -- Configure this deployment

```bash
cd infra/environments/dev
cp terraform.tfvars.example terraform.tfvars
```

Open `terraform.tfvars` and fill in anything you want to change (region,
project/environment name) -- every value has a working default, so an empty
file is fine to start with.

### Step 6 -- Initialize Terraform

```bash
terraform init -backend-config=backend.hcl
```

### Step 7 -- Create the ECR repositories (first apply)

Each of the 4 services needs its own container image pushed before its
AgentCore Runtime can be created, so the first apply only targets the 4 ECR
repositories:

```bash
terraform apply \
  -target=module.orchestrator.aws_ecr_repository.this \
  -target=module.api_security_agent.aws_ecr_repository.this \
  -target=module.agentic_security_agent.aws_ecr_repository.this \
  -target=module.approval_agent.aws_ecr_repository.this
```

### Step 8 -- Build and push the service images

From the repository root:

```bash
cd ../../..
scripts/build-and-push.sh <version>   # e.g. scripts/build-and-push.sh v0.1.0 (omit to default to the current git short SHA)
```

This builds all 4 images (`linux/arm64`) and pushes them to the repositories
created in Step 7, tagged with `<version>` -- **never `:latest`**, so a
later rebuild can't silently go stale without Terraform noticing it (this
project hit exactly that bug once with a `:latest`-tagged deployment). It
prints the exact command for Step 9 when done.

### Step 9 -- Deploy the full stack

```bash
cd infra/environments/dev
terraform apply -var="image_tag=<version>"   # the same <version> from Step 8
```

This creates everything else: the Gateway, the 4 AgentCore Runtimes, the
interceptor Lambda, the Approval Agent's DynamoDB table and KMS key, and all
IAM roles/policies.

### Step 10 -- Verify the deployment

```bash
cd ../../..
scripts/verify.sh
```

Read-only checks (all 4 runtimes `READY`, Gateway targets synced) plus one
real end-to-end question through the Orchestrator. Expect `6 passed, 0
failed`.

### Step 11 -- Run the demo

```bash
scripts/start-demo.sh
```

Launches the demo UI at `http://localhost:8000`. Open it in a browser, ask
a question, and try triggering an approval (e.g. "please submit feedback
about...") or a DAST-related question to see the human-in-the-loop flow.
See `ui/README.md` for the full scenario list and what each button does.

## Demo scenarios

`ui/README.md` maps out all of this project's demo scenarios (normal
requests in both domains, deterministic sendFeedback approval/denial, DAST
human-in-the-loop approval/denial/additional-instruction) to concrete UI
actions, and explains the "actual execution" panel -- a CloudWatch-backed
check that distinguishes what the agent *says* it did from whether the real
MCP tool call actually happened.

## Conventions

- Resource naming: `asl-<component>-<env>`
- Tags on every resource: `Project=<project_name>`, `Environment`, `ManagedBy=terraform`, `Phase`
- No secrets or Terraform state committed to git (see `.gitignore`)
- Container images are versioned (`image_tag`), never `:latest`, for any
  deployment created via the steps above

## Tearing it down

```bash
cd infra/environments/dev
terraform destroy
```

One known gotcha: the ECR repositories don't have `force_delete` enabled, so
`destroy` will fail on any repository that still contains images. Either
delete the images first (`aws ecr batch-delete-image` / `aws ecr
delete-repository --force`) or re-run `destroy` after clearing them. This
does not delete the Terraform state bucket from Step 4 -- remove that
separately (`infra/bootstrap`) if you want a fully clean account.

## Internal-only files

If you're working from a full development checkout of this project (rather
than a plain `git clone`), you may also see a `docs/` directory and a
handful of extra scripts under `scripts/` (`demo_interactive.sh`,
`test_approval_flow.sh`, `test_hitl_flow.sh`, `approval_decide.py`). Both
are gitignored on purpose -- `docs/` holds internal design/phase notes not
meant for client sharing, and those scripts hardcode a specific
deployment's own resource IDs for quick local debugging. Neither is part of
a fresh clone, and neither is required by the steps above -- the UI and the
scripts in this README are the supported path.
