#!/usr/bin/env bash
set -euo pipefail

fail=0

check() {
  local name="$1" cmd="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "MISSING: $name ($cmd not found on PATH)"
    fail=1
    return
  fi
}

check "AWS CLI" aws
check "Terraform" terraform
check "Python 3" python3
check "Docker" docker

if [ "$fail" -eq 0 ]; then
  echo "aws:        $(aws --version 2>&1)"
  echo "terraform:  $(terraform version | head -n1)"
  echo "python3:    $(python3 --version)"
  echo "docker:     $(docker --version)"
fi

echo
if aws sts get-caller-identity >/dev/null 2>&1; then
  echo "AWS credentials: OK ($(aws sts get-caller-identity --query Arn --output text))"
else
  echo "AWS credentials: NOT configured or invalid (aws sts get-caller-identity failed)"
  fail=1
fi

exit "$fail"
