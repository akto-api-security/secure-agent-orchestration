"""Configuration for the Akto Guardrail SDK.

Every value is read from the environment or supplied directly by the
caller — nothing is hardcoded. No credential has a default; a missing
required value raises immediately rather than falling back silently.
"""

import os
from dataclasses import dataclass
from typing import Optional

from .exceptions import AktoGuardrailConfigError

DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_API_KEY_HEADER = "Authorization"


@dataclass(frozen=True)
class AktoGuardrailConfig:
    base_url: str
    api_key: Optional[str] = None
    api_key_header: str = DEFAULT_API_KEY_HEADER
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    environment: Optional[str] = None
    account_id: Optional[str] = None

    def __post_init__(self):
        if not self.base_url:
            raise AktoGuardrailConfigError("AktoGuardrailConfig.base_url is required")
        if self.timeout_seconds <= 0:
            raise AktoGuardrailConfigError("AktoGuardrailConfig.timeout_seconds must be > 0")

    @classmethod
    def from_env(cls, prefix: str = "AKTO_GUARDRAIL_") -> "AktoGuardrailConfig":
        """Build config from environment variables:

        - `<prefix>URL`              required — base URL of the Guardrail Engine.
        - `<prefix>API_KEY`          optional — credential, sent as a header only.
        - `<prefix>API_KEY_HEADER`   optional — overrides the header name. Defaults to `Authorization`.
        - `<prefix>TIMEOUT_SECONDS`  optional — default 5.
        - `<prefix>ENVIRONMENT`      optional — free-form identifier, for this SDK's own use only.
        - `<prefix>ACCOUNT_ID`       optional — sent as `akto_account_id` if set.
        """
        base_url = os.environ.get(f"{prefix}URL")
        if not base_url:
            raise AktoGuardrailConfigError(f"{prefix}URL is required but not set")

        timeout_raw = os.environ.get(f"{prefix}TIMEOUT_SECONDS")
        try:
            timeout_seconds = float(timeout_raw) if timeout_raw else DEFAULT_TIMEOUT_SECONDS
        except ValueError as exc:
            raise AktoGuardrailConfigError(
                f"{prefix}TIMEOUT_SECONDS must be a number, got {timeout_raw!r}"
            ) from exc

        return cls(
            base_url=base_url,
            api_key=os.environ.get(f"{prefix}API_KEY") or None,
            api_key_header=os.environ.get(f"{prefix}API_KEY_HEADER", DEFAULT_API_KEY_HEADER),
            timeout_seconds=timeout_seconds,
            environment=os.environ.get(f"{prefix}ENVIRONMENT") or None,
            account_id=os.environ.get(f"{prefix}ACCOUNT_ID") or None,
        )
