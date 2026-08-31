"""Public interface of the Akto Guardrail SDK.

    client = AktoGuardrailClient(config)
    decision = client.evaluate(request_context)

`evaluate()` either returns a `GuardrailDecision` or raises an
`AktoGuardrailError` subclass — it never returns a decision on a failure
path.
"""

import json
import time
import urllib.error
import urllib.request
from typing import Callable, Optional, Tuple
from urllib.parse import urljoin

from . import contract
from .config import AktoGuardrailConfig
from .exceptions import (
    AktoGuardrailAuthenticationError,
    AktoGuardrailHTTPError,
    AktoGuardrailMalformedResponseError,
    AktoGuardrailTimeoutError,
    AktoGuardrailUnexpectedDecisionError,
)
from .models import GuardrailDecision, RequestContext

# (method, url, headers, body_bytes, timeout_seconds) -> (status_code, response_body_bytes)
# Injectable so callers/tests can supply a transport without a real network call.
TransportFunc = Callable[[str, str, dict, bytes, float], Tuple[int, bytes]]


def _default_transport(method: str, url: str, headers: dict, body: bytes, timeout_seconds: float) -> Tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class AktoGuardrailClient:
    """Client for the Akto Guardrail Engine. No retries — a failed attempt
    raises rather than being silently retried."""

    def __init__(self, config: AktoGuardrailConfig, *, transport: Optional[TransportFunc] = None):
        self._config = config
        self._transport = transport or _default_transport

    def evaluate(self, request_context: RequestContext) -> GuardrailDecision:
        path, headers, body = contract.build_request(request_context, self._config)
        url = urljoin(self._config.base_url.rstrip("/") + "/", path.lstrip("/"))

        start = time.monotonic()
        try:
            status_code, raw_body = self._transport(
                contract.HTTP_METHOD, url, headers, body, self._config.timeout_seconds
            )
        except TimeoutError as exc:
            raise AktoGuardrailTimeoutError(
                f"Akto Guardrail Engine did not respond within {self._config.timeout_seconds}s"
            ) from exc
        except OSError as exc:
            raise AktoGuardrailHTTPError(f"failed to reach Akto Guardrail Engine: {exc}") from exc
        latency_ms = (time.monotonic() - start) * 1000

        if status_code in (401, 403):
            raise AktoGuardrailAuthenticationError(
                f"Akto Guardrail Engine rejected credentials (HTTP {status_code})",
                status_code=status_code,
            )
        if not (200 <= status_code < 300):
            raise AktoGuardrailHTTPError(
                f"Akto Guardrail Engine returned HTTP {status_code}", status_code=status_code
            )

        try:
            parsed = contract.parse_response(status_code, raw_body)
        except json.JSONDecodeError as exc:
            raise AktoGuardrailMalformedResponseError(f"non-JSON response: {exc}") from exc
        except ValueError as exc:
            raise AktoGuardrailMalformedResponseError(str(exc)) from exc
        except KeyError as exc:
            raise AktoGuardrailUnexpectedDecisionError(
                f"unrecognized decision from Akto Guardrail Engine: {exc.args[0]!r}"
            ) from exc

        return GuardrailDecision(
            decision=parsed["decision"],
            reason=parsed.get("reason", ""),
            reference_id=parsed.get("reference_id"),
            status_code=status_code,
            latency_ms=latency_ms,
            raw_response=parsed.get("raw"),
        )
