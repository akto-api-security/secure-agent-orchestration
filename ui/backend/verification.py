"""The "agent said vs. actually executed" check (see docs/architecture.md,
Phase 5: tool_name/execution verification exists for exactly this reason).

Ports scripts/demo_interactive.sh's `verify_tool_execution()` exactly:
gateway_tool.py only logs "Tool call succeeded: tool=<namespaced_tool_name>"
on a real, executed Gateway/MCP call -- never on a denied/cancelled one. A
CloudWatch Logs filter for that literal line in the delegated agent's own
log group is the same non-invented signal the existing bash demo scripts
already use as evidence, not a new mechanism.

Never guesses: returns UNKNOWN (not EXECUTED or NOT_EXECUTED) whenever the
log group can't be resolved or read, exactly like the bash version's
try_logs degrading gracefully on a logs:FilterLogEvents permission gap.
"""

import logging
import time
from dataclasses import dataclass

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .config import settings

logger = logging.getLogger(__name__)

_logs_client = boto3.client("logs", region_name=settings.region)


@dataclass
class ExecutionVerdict:
    verdict: str  # "EXECUTED" | "NOT_EXECUTED" | "UNKNOWN"
    detail: str
    log_lines: list[str]


def verify_tool_execution(domain: str | None, tool_name: str | None, start_time_ms: int) -> ExecutionVerdict:
    if not domain or not tool_name:
        return ExecutionVerdict("UNKNOWN", "No domain/tool_name to check yet.", [])

    log_group = settings.delegate_log_group(domain)
    if not log_group:
        return ExecutionVerdict("UNKNOWN", f"No delegated-agent log group resolved for domain={domain}.", [])

    try:
        response = _logs_client.filter_log_events(
            logGroupName=log_group,
            startTime=start_time_ms,
            filterPattern=f'"Tool call succeeded" "{tool_name}"',
        )
    except (ClientError, BotoCoreError) as exc:
        logger.warning("Could not read %s: %s", log_group, exc)
        return ExecutionVerdict("UNKNOWN", f"Could not read {log_group} (likely missing logs:FilterLogEvents).", [])

    messages = [e["message"] for e in response.get("events", [])]
    if messages:
        return ExecutionVerdict("EXECUTED", f"Found a real 'Tool call succeeded' log line for {tool_name}.", messages)
    return ExecutionVerdict("NOT_EXECUTED", f"No 'Tool call succeeded' log line found yet for {tool_name} in {log_group}.", [])


def now_ms() -> int:
    return int(time.time() * 1000)
