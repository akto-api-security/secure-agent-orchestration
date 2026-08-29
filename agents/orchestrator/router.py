"""Deterministic keyword routing between the two Phase 2 delegated agents.

Uses substring matching against the domain lists from the Phase 3 brief
rather than an LLM call: the routing surface is small and fixed, so a
keyword match is cheaper, fully predictable, and easier to reason about than
adding a model round trip (and the IAM/model permissions that would need).
"""

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class Domain(str, Enum):
    API_SECURITY = "api_security"
    AGENTIC_SECURITY = "agentic_security"


# Phrases taken directly from the Phase 3 brief's domain lists, plus
# "prompt injection" (used in the brief's own routing examples for the
# Agentic Security Agent even though it isn't in the bulleted domain list).
API_SECURITY_KEYWORDS = [
    "api security",
    "dast",
    "api vulnerab",  # matches vulnerability/vulnerabilities
    "api testing",
    "api test",  # matches test/tests
]

AGENTIC_SECURITY_KEYWORDS = [
    "atlas",
    "argus",
    "agentic security",
    "agentic",
    "mcp security",
    "a2a security",
    "agent security",
    "ai security",
    "prompt injection",
]


@dataclass
class RouteResult:
    domain: Domain | None  # None means ambiguous -- ask the user to clarify
    matched_keywords: list[str]


def classify(question: str) -> RouteResult:
    normalized = question.lower()

    api_hits = [kw for kw in API_SECURITY_KEYWORDS if kw in normalized]
    agentic_hits = [kw for kw in AGENTIC_SECURITY_KEYWORDS if kw in normalized]

    if api_hits and not agentic_hits:
        return RouteResult(domain=Domain.API_SECURITY, matched_keywords=api_hits)
    if agentic_hits and not api_hits:
        return RouteResult(domain=Domain.AGENTIC_SECURITY, matched_keywords=agentic_hits)

    # Neither matched, or both matched (genuinely ambiguous either way) --
    # the brief's prescribed fallback is to ask the user to clarify rather
    # than guess.
    logger.info(
        "No unambiguous domain match (api_hits=%s, agentic_hits=%s)", api_hits, agentic_hits
    )
    return RouteResult(domain=None, matched_keywords=api_hits + agentic_hits)
