#!/usr/bin/env bash
# Downloads two copies of the static OPA binary:
#   bin/opa        -- linux/arm64, what actually gets zipped into the Lambda
#                      deployment package (matches the Terraform module's
#                      `architectures = ["arm64"]`). Not runnable on a
#                      non-Linux dev machine -- that's expected, it's a
#                      deployment artifact, not a local test tool.
#   bin/opa-local   -- matches whatever OS/arch this script is run on, for
#                      running `opa test` / the pytest suite locally.
#
# Not run automatically -- run it yourself before `terraform apply` on the
# gateway-interceptor module, per this project's standing preference for the
# user to run side-effecting/build commands directly.
set -euo pipefail

OPA_VERSION="${OPA_VERSION:-v1.20.1}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HERE}/bin"

# Filename pattern (opa_<os>_<arch>) confirmed against
# https://www.openpolicyagent.org/docs/latest/#running-opa -- no "_static"
# suffix in current OPA docs, so it isn't assumed here.
detect_local_asset() {
  local os arch
  os="$(uname -s)"
  arch="$(uname -m)"
  case "${os}" in
    Darwin) os="darwin" ;;
    Linux) os="linux" ;;
    *)
      echo "Unrecognized OS '${os}' -- download the matching binary from" >&2
      echo "https://www.openpolicyagent.org/docs/latest/#running-opa yourself" >&2
      echo "and place it at ${BIN_DIR}/opa-local" >&2
      return 1
      ;;
  esac
  case "${arch}" in
    arm64|aarch64) arch="arm64" ;;
    x86_64|amd64) arch="amd64" ;;
    *)
      echo "Unrecognized architecture '${arch}' -- see note above." >&2
      return 1
      ;;
  esac
  echo "opa_${os}_${arch}"
}

mkdir -p "${BIN_DIR}"

echo "Downloading OPA ${OPA_VERSION} (linux/arm64 -- Lambda deployment artifact) ..."
curl -L -o "${BIN_DIR}/opa" \
  "https://openpolicyagent.org/downloads/${OPA_VERSION}/opa_linux_arm64"
chmod +x "${BIN_DIR}/opa"
echo "-> ${BIN_DIR}/opa (not executable on this machine unless it's linux/arm64 -- expected)"

LOCAL_ASSET="$(detect_local_asset)"
echo "Downloading OPA ${OPA_VERSION} (${LOCAL_ASSET} -- for running tests on this machine) ..."
curl -L -o "${BIN_DIR}/opa-local" \
  "https://openpolicyagent.org/downloads/${OPA_VERSION}/${LOCAL_ASSET}"
chmod +x "${BIN_DIR}/opa-local"

echo
echo "OPA local test binary ready:"
"${BIN_DIR}/opa-local" version

echo
echo "Next steps:"
echo "  1. Run policy tests:  ${BIN_DIR}/opa-local test policies/ -v"
echo "  2. Run handler tests: OPA_BIN_PATH=${BIN_DIR}/opa-local python3 -m pytest tests/ -v"
echo "  3. terraform init/plan/apply the gateway-interceptor module (packages bin/opa, the linux/arm64 copy, via the archive_file data source)"
