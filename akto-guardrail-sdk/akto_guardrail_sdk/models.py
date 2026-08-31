"""Normalized request/decision models for the Akto Guardrail SDK."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class Decision(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


@dataclass(frozen=True)
class RequestContext:
    """Normalized input to `AktoGuardrailClient.evaluate()`."""

    correlation_id: str
    tool_name: str
    bare_tool_name: str
    mcp_target: Optional[str]
    tool_arguments: Dict[str, Any]
    requesting_agent: Optional[str] = None
    session_context: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None

    def to_normalized_dict(self) -> Dict[str, Any]:
        data = {
            "correlation_id": self.correlation_id,
            "tool_name": self.tool_name,
            "bare_tool_name": self.bare_tool_name,
            "mcp_target": self.mcp_target,
            "tool_arguments": self.tool_arguments,
            "requesting_agent": self.requesting_agent,
            "session_context": self.session_context,
            "session_id": self.session_id,
        }
        if self.extra:
            data.update(self.extra)
        return {k: v for k, v in data.items() if v is not None}


@dataclass(frozen=True)
class GuardrailDecision:
    """Normalized output of `AktoGuardrailClient.evaluate()`."""

    decision: Decision
    reason: str = ""
    reference_id: Optional[str] = None
    status_code: Optional[int] = None
    latency_ms: float = 0.0
    raw_response: Optional[Dict[str, Any]] = field(default=None, repr=False)
