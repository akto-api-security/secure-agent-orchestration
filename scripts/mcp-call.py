#!/usr/bin/env python3
"""Call the MCP Gateway directly with SigV4, bypassing the agent.

Usage:
  scripts/mcp-call.py list
  scripts/mcp-call.py call searchDocumentation '{"query": "API security testing"}'

Tool names are namespaced <target>___<tool> by the Gateway; a bare name is
prefixed with MCP_TARGET_PREFIX.
"""

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

SERVICE = "bedrock-agentcore"
REGION = os.environ.get("AWS_REGION", "us-east-1")
TARGET_PREFIX = os.environ.get("MCP_TARGET_PREFIX", "mac-akto-api-mcp")
TIMEOUT_SECONDS = int(os.environ.get("MCP_TIMEOUT_SECONDS", "900"))
TF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "infra", "environments", "akto-demo")


def _run(command: list[str]) -> str:
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()


def _gateway_url() -> str:
    url = os.environ.get("MCP_GATEWAY_URL")
    if url:
        return url
    return _run(["terraform", f"-chdir={TF_DIR}", "output", "-raw", "mcp_gateway_url"])


def _credentials() -> dict:
    return json.loads(_run(["aws", "configure", "export-credentials", "--format", "json"]))


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


def _signed_headers(url: str, body: str, credentials: dict) -> dict:
    parsed = urllib.parse.urlparse(url)
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body.encode()).hexdigest()

    headers = {
        "content-type": "application/json",
        "host": parsed.netloc,
        "x-amz-date": amz_date,
    }
    token = credentials.get("SessionToken")
    if token:
        headers["x-amz-security-token"] = token

    signed_header_names = ";".join(sorted(headers))
    canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in sorted(headers))
    canonical_request = "\n".join(
        ["POST", parsed.path or "/", "", canonical_headers, signed_header_names, payload_hash]
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


def _post(payload: dict) -> int:
    url = _gateway_url()
    body = json.dumps(payload)
    request = urllib.request.Request(
        url, data=body.encode(), headers=_signed_headers(url, body, _credentials()), method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status, text = response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        status, text = error.code, error.read().decode()

    print(f"HTTP {status}")
    try:
        print(json.dumps(json.loads(text), indent=2))
    except json.JSONDecodeError:
        print(text)
    return 0 if status == 200 else 1


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] not in {"list", "call"}:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    if args[0] == "list":
        return _post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    if len(args) < 2:
        print("call requires a tool name", file=sys.stderr)
        return 2

    name = args[1] if "___" in args[1] else f"{TARGET_PREFIX}___{args[1]}"
    arguments = json.loads(args[2]) if len(args) > 2 else {}
    return _post(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )


if __name__ == "__main__":
    sys.exit(main())
