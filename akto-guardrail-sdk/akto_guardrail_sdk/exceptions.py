"""Exception hierarchy for the Akto Guardrail SDK.

Callers should catch `AktoGuardrailError` and treat it as a failure to
evaluate — this SDK never maps a failure to a successful decision.
"""


class AktoGuardrailError(Exception):
    """Base class for every error this SDK raises."""


class AktoGuardrailConfigError(AktoGuardrailError):
    """The client is misconfigured (e.g. no base URL)."""


class AktoGuardrailTimeoutError(AktoGuardrailError):
    """The Guardrail Engine did not respond within the configured timeout."""


class AktoGuardrailHTTPError(AktoGuardrailError):
    """A non-2xx HTTP response, or the connection itself failed."""

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class AktoGuardrailAuthenticationError(AktoGuardrailHTTPError):
    """The Guardrail Engine rejected the configured credentials (401/403)."""


class AktoGuardrailMalformedResponseError(AktoGuardrailError):
    """The response could not be parsed into the expected decision shape."""


class AktoGuardrailUnexpectedDecisionError(AktoGuardrailError):
    """The response parsed, but its decision value wasn't recognized."""
