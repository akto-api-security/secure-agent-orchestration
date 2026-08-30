"""Fetches recent CloudWatch log events across every log group this UI
knows about, merged and sorted, for the standalone log viewer page
(ui/static/logs.html). Not tied to any single request/response -- this is
a general "what's happening across the whole stack right now" view, meant
to run alongside the main workflow page while a demo is in progress.

Degrades gracefully per log group (missing permission, group doesn't
exist yet) rather than failing the whole request -- same principle as
verification.py's UNKNOWN handling and demo_interactive.sh's try_logs.
"""

import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .config import settings

logger = logging.getLogger(__name__)

_logs_client = boto3.client("logs", region_name=settings.region)

_MAX_EVENTS_PER_GROUP = 200


def fetch_recent_logs(since_ms: int) -> list[dict]:
    events: list[dict] = []
    for component, log_group in settings.all_log_groups().items():
        try:
            response = _logs_client.filter_log_events(
                logGroupName=log_group,
                startTime=since_ms,
                limit=_MAX_EVENTS_PER_GROUP,
            )
        except (ClientError, BotoCoreError) as exc:
            logger.warning("Could not read %s (%s): %s", log_group, component, exc)
            events.append({
                "ts": since_ms,
                "component": component,
                "message": f"(could not read this log group -- {exc})",
                "error": True,
            })
            continue

        for item in response.get("events", []):
            events.append({
                "ts": item.get("timestamp", since_ms),
                "component": component,
                "message": item.get("message", "").rstrip("\n"),
                "error": False,
            })

    events.sort(key=lambda e: e["ts"])
    return events
