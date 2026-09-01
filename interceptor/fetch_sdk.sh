#!/usr/bin/env bash
# Fetches the Akto Guardrail SDK from its real, externally-maintained
# source and vendors it into akto_guardrail_sdk/ here -- committed as part
# of this interceptor's own code, not fetched at deploy/runtime.
#
# Requires AKTO_SDK_GIT_TOKEN (a GitHub PAT with read access to the SDK's
# repo) in the environment.
#
# Not run automatically -- run it yourself, per this project's standing
# preference for the user to run side-effecting/build commands directly.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${HERE}/akto_guardrail_sdk"
: "${AKTO_SDK_GIT_TOKEN:?AKTO_SDK_GIT_TOKEN must be set (a GitHub PAT with read access to the SDK repo)}"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"' EXIT

echo "Fetching the Akto Guardrail SDK ..."
pip install --quiet --no-deps --target "${WORKDIR}" \
  "git+https://${AKTO_SDK_GIT_TOKEN}@github.com/akto-api-security/secure-agent-orchestration.git#subdirectory=akto-guardrail-sdk"

rm -rf "${DEST}"
cp -r "${WORKDIR}/akto_guardrail_sdk" "${DEST}"
find "${DEST}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

echo "-> ${DEST} refreshed. Commit this directory as part of the interceptor's own code."
