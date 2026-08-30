"""Resolves the runtime ARNs/log groups the demo UI needs: environment
variable first, `terraform output` fallback -- the same resolution order
scripts/demo_interactive.sh already uses (see its `tf_output()`), ported to
Python so the UI backend doesn't require a shell wrapper to run standalone
(scripts/start-demo.sh sets the env vars directly and skips the Terraform
lookup entirely).

No account ID, runtime ID, or region is hardcoded here.
"""

import functools
import os
import subprocess

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TF_DIR = os.path.join(_ROOT_DIR, "infra", "environments", "dev")


@functools.lru_cache(maxsize=None)
def _tf_output(name: str) -> str:
    try:
        result = subprocess.run(
            ["terraform", f"-chdir={_TF_DIR}", "output", "-raw", name],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _resolve(env_var: str, tf_output_name: str) -> str:
    return os.environ.get(env_var) or _tf_output(tf_output_name)


def runtime_id_from_arn(arn: str) -> str:
    return arn.rsplit("/", 1)[-1]


class Settings:
    def __init__(self) -> None:
        self.orchestrator_arn = _resolve("ORCHESTRATOR_ARN", "orchestrator_runtime_arn")
        self.approval_agent_arn = _resolve("APPROVAL_AGENT_ARN", "approval_agent_runtime_arn")
        self.api_agent_arn = _resolve("API_AGENT_ARN", "api_security_agent_runtime_arn")
        self.agentic_agent_arn = _resolve("AGENTIC_AGENT_ARN", "agentic_security_agent_runtime_arn")
        self.interceptor_log_group = _resolve("INTERCEPTOR_LOG_GROUP", "interceptor_log_group_name")

        region_env = os.environ.get("REGION") or os.environ.get("AGENT_REGION")
        if not region_env and self.orchestrator_arn:
            # arn:aws:<service>:<region>:<account>:... -- same derivation
            # demo_interactive.sh uses, so this works against any region
            # without a separate variable to keep in sync.
            parts = self.orchestrator_arn.split(":")
            region_env = parts[3] if len(parts) > 3 else None
        self.region = region_env or "us-east-1"

    def delegate_log_group(self, domain: str) -> str | None:
        arn = {"api_security": self.api_agent_arn, "agentic_security": self.agentic_agent_arn}.get(domain)
        if not arn:
            return None
        return f"/aws/bedrock-agentcore/runtimes/{runtime_id_from_arn(arn)}-DEFAULT"

    def all_log_groups(self) -> dict[str, str]:
        """Every log group this UI knows how to derive, labeled for display.
        Orchestrator/Approval Agent/both delegated agents are all plain
        AgentCore Runtimes, so their log group name follows the same
        `/aws/bedrock-agentcore/runtimes/<runtime-id>-DEFAULT` pattern; the
        interceptor is a separate Lambda log group, already exposed as a
        Terraform output."""
        groups = {}
        if self.orchestrator_arn:
            groups["Orchestrator"] = f"/aws/bedrock-agentcore/runtimes/{runtime_id_from_arn(self.orchestrator_arn)}-DEFAULT"
        if self.api_agent_arn:
            groups["Delegated Agent (API Security)"] = self.delegate_log_group("api_security")
        if self.agentic_agent_arn:
            groups["Delegated Agent (Agentic Security)"] = self.delegate_log_group("agentic_security")
        if self.approval_agent_arn:
            groups["Approval Agent"] = f"/aws/bedrock-agentcore/runtimes/{runtime_id_from_arn(self.approval_agent_arn)}-DEFAULT"
        if self.interceptor_log_group:
            groups["Interceptor"] = self.interceptor_log_group
        return groups

    def is_ready(self) -> bool:
        return bool(self.orchestrator_arn and self.approval_agent_arn)


settings = Settings()
