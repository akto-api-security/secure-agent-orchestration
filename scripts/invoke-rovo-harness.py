#!/usr/bin/env python3
"""Invoke an AgentCore Harness (InvokeHarness API via SigV4, no boto3)."""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

SERVICE = "bedrock-agentcore"
REGION = os.environ.get("AWS_REGION", "us-east-1")
DEFAULT_QUALIFIER = "DEFAULT"
HARNESS_ENDPOINT = os.environ.get(
    "HARNESS_ENDPOINT",
    f"https://bedrock-agentcore.{REGION}.amazonaws.com/harnesses/invoke",
)
TF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "infra", "environments", "akto-demo")


def _aws_cli(*args: str) -> list[str]:
    command = ["aws"]
    profile = os.environ.get("AWS_PROFILE")
    if profile:
        command.extend(["--profile", profile])
    command.extend(args)
    return command


def _run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() or f"exit {result.returncode}"
        print(f"command failed: {' '.join(command)}\n{detail}", file=sys.stderr)
        raise SystemExit(1)
    return result.stdout.strip()


def _credentials() -> dict:
    access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    if access_key and secret_key:
        creds = {"AccessKeyId": access_key, "SecretAccessKey": secret_key}
        token = os.environ.get("AWS_SESSION_TOKEN")
        if token:
            creds["SessionToken"] = token
        return creds
    return json.loads(_run(_aws_cli("configure", "export-credentials", "--format", "process")))


def _harness_arn() -> str:
    explicit = os.environ.get("ROVO_HARNESS_ARN")
    if explicit:
        return explicit
    return _run(["terraform", f"-chdir={TF_DIR}", "output", "-raw", "rovo_harness_arn"])


def _session_id() -> str:
    explicit = os.environ.get("HARNESS_SESSION_ID")
    if explicit:
        return explicit
    return f"session-{uuid.uuid4()}"


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


def _signed_headers(url: str, body: str, credentials: dict, session_id: str) -> dict:
    parsed = urllib.parse.urlparse(url)
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body.encode()).hexdigest()

    headers = {
        "content-type": "application/json",
        "host": parsed.netloc,
        "x-amz-date": amz_date,
        "x-amzn-bedrock-agentcore-runtime-session-id": session_id,
    }
    token = credentials.get("SessionToken")
    if token:
        headers["x-amz-security-token"] = token

    signed_header_names = ";".join(sorted(headers))
    canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in sorted(headers))
    canonical_query = urllib.parse.urlencode(
        urllib.parse.parse_qsl(parsed.query, keep_blank_values=True),
        quote_via=urllib.parse.quote,
    )
    canonical_request = "\n".join(
        [
            "POST",
            parsed.path or "/",
            canonical_query,
            canonical_headers,
            signed_header_names,
            payload_hash,
        ]
    )

    scope = f"{date_stamp}/{REGION}/{SERVICE}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )

    signing_key = _sign(f"AWS4{credentials['SecretAccessKey']}".encode(), date_stamp)
    for part in (REGION, SERVICE, "aws4_request"):
        signing_key = _sign(signing_key, part)
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()

    headers["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={credentials['AccessKeyId']}/{scope}, "
        f"SignedHeaders={signed_header_names}, Signature={signature}"
    )
    headers["accept"] = "application/json, text/event-stream"
    return headers


def invoke_harness(*, harness_arn: str, prompt: str, qualifier: str, session_id: str) -> int:
    query = urllib.parse.urlencode({"harnessArn": harness_arn, "qualifier": qualifier})
    url = f"{HARNESS_ENDPOINT}?{query}"
    body = json.dumps(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ],
        }
    )
    request = urllib.request.Request(
        url,
        data=body.encode(),
        headers=_signed_headers(url, body, _credentials(), session_id),
        method="POST",
    )
    print(f"harness: {harness_arn}", file=sys.stderr)
    print(f"session: {session_id}", file=sys.stderr)
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            print(f"HTTP {response.status}", file=sys.stderr)
            while True:
                chunk = response.read(4096)
                if not chunk:
                    break
                sys.stdout.write(chunk.decode("utf-8", errors="replace"))
            sys.stdout.write("\n")
            return 0
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}", file=sys.stderr)
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1


def main() -> int:
    prompt = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "I uploaded a Backlog Guide. Please read it and organize my Jira backlog for this sprint."
    )
    qualifier = os.environ.get("HARNESS_QUALIFIER", DEFAULT_QUALIFIER)
    return invoke_harness(
        harness_arn=_harness_arn(),
        prompt=prompt,
        qualifier=qualifier,
        session_id=_session_id(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
