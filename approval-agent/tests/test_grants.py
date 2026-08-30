"""grants.py issues/verifies KMS-signed tokens. Unit tests replace the KMS
client with a fake that behaves like real Sign/Verify (same key -> same
signature, mismatched key or tampered payload -> SignatureValid=False) so
the actual binding/expiry/tamper logic in grants.py is exercised without a
real AWS call.
"""

import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GRANT_KMS_KEY_ID", "arn:aws:kms:us-east-1:000000000000:key/fake-key")

import grants  # noqa: E402


class _FakeKMS:
    """Deterministic stand-in for AWS KMS Sign/Verify: 'signs' by hashing
    KeyId+Message together, so a signature only verifies against the exact
    same key and an unmodified message -- the same properties a real
    asymmetric signature has for this module's purposes."""

    def sign(self, KeyId, Message, MessageType, SigningAlgorithm):
        return {"Signature": hashlib.sha256(KeyId.encode() + Message).digest()}

    def verify(self, KeyId, Message, MessageType, Signature, SigningAlgorithm):
        expected = hashlib.sha256(KeyId.encode() + Message).digest()
        return {"SignatureValid": Signature == expected}


def _patch_kms(monkeypatch):
    monkeypatch.setattr(grants, "_kms", _FakeKMS())


def test_issue_then_verify_round_trip_succeeds(monkeypatch):
    _patch_kms(monkeypatch)
    args_hash = grants.arguments_hash({"feedback": "x"})
    grant = grants.issue_grant(
        reference_id="appr-1", correlation_id="corr-1", tool_name="mac-akto-api-mcp___sendFeedback",
        target="mac-akto-api-mcp", args_hash=args_hash,
    )
    payload = grants.verify_grant(grant, tool_name="mac-akto-api-mcp___sendFeedback", target="mac-akto-api-mcp", args_hash=args_hash)
    assert payload["reference_id"] == "appr-1"


def test_verify_rejects_wrong_tool(monkeypatch):
    _patch_kms(monkeypatch)
    args_hash = grants.arguments_hash({"feedback": "x"})
    grant = grants.issue_grant(reference_id="appr-1", correlation_id="c", tool_name="mac-akto-api-mcp___sendFeedback", target="mac-akto-api-mcp", args_hash=args_hash)
    try:
        grants.verify_grant(grant, tool_name="mac-akto-api-mcp___getPage", target="mac-akto-api-mcp", args_hash=args_hash)
        assert False, "expected GrantError"
    except grants.GrantError as exc:
        assert "different tool" in str(exc)


def test_verify_rejects_wrong_target(monkeypatch):
    _patch_kms(monkeypatch)
    args_hash = grants.arguments_hash({"feedback": "x"})
    grant = grants.issue_grant(reference_id="appr-1", correlation_id="c", tool_name="mac-akto-api-mcp___sendFeedback", target="mac-akto-api-mcp", args_hash=args_hash)
    try:
        grants.verify_grant(grant, tool_name="mac-akto-api-mcp___sendFeedback", target="mac-akto-ai-mcp", args_hash=args_hash)
        assert False, "expected GrantError"
    except grants.GrantError as exc:
        assert "different target" in str(exc)


def test_verify_rejects_changed_arguments(monkeypatch):
    _patch_kms(monkeypatch)
    original_hash = grants.arguments_hash({"feedback": "x"})
    grant = grants.issue_grant(reference_id="appr-1", correlation_id="c", tool_name="t", target="tgt", args_hash=original_hash)
    changed_hash = grants.arguments_hash({"feedback": "SOMETHING ELSE"})
    try:
        grants.verify_grant(grant, tool_name="t", target="tgt", args_hash=changed_hash)
        assert False, "expected GrantError"
    except grants.GrantError as exc:
        assert "changed after approval" in str(exc)


def test_verify_rejects_expired_grant(monkeypatch):
    _patch_kms(monkeypatch)
    monkeypatch.setattr(grants, "GRANT_TTL_SECONDS", -10)  # already expired the moment it's issued
    args_hash = grants.arguments_hash({})
    grant = grants.issue_grant(reference_id="appr-1", correlation_id="c", tool_name="t", target="tgt", args_hash=args_hash)
    try:
        grants.verify_grant(grant, tool_name="t", target="tgt", args_hash=args_hash)
        assert False, "expected GrantError"
    except grants.GrantError as exc:
        assert "expired" in str(exc)


def test_verify_rejects_signature_from_an_untrusted_key(monkeypatch):
    _patch_kms(monkeypatch)
    args_hash = grants.arguments_hash({})
    payload_bytes = json.dumps(
        {"v": 1, "reference_id": "appr-1", "correlation_id": "c", "tool_name": "t", "target": "tgt",
         "arguments_hash": args_hash, "decision": "approve", "issued_at": 0, "expires_at": 2**31},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    # Simulate an attacker who signed with their OWN (different) KMS key,
    # then relabeled the envelope's informational key_id field to claim it's
    # ours. Verification must ignore that claim and only ever check against
    # GRANT_KMS_KEY_ID -- this should fail exactly like a bad signature.
    attacker_signature = hashlib.sha256(b"attacker-key" + payload_bytes).digest()
    forged = json.dumps({
        "payload": grants._b64u_encode(payload_bytes),
        "signature": grants._b64u_encode(attacker_signature),
        "key_id": grants.GRANT_KMS_KEY_ID,
    })
    try:
        grants.verify_grant(forged, tool_name="t", target="tgt", args_hash=args_hash)
        assert False, "expected GrantError"
    except grants.GrantError as exc:
        assert "invalid grant signature" in str(exc)


def test_verify_rejects_malformed_grant(monkeypatch):
    _patch_kms(monkeypatch)
    try:
        grants.verify_grant("not even json", tool_name="t", target="tgt", args_hash="x")
        assert False, "expected GrantError"
    except grants.GrantError as exc:
        assert "malformed grant" in str(exc)


def test_arguments_hash_is_order_independent():
    assert grants.arguments_hash({"a": 1, "b": 2}) == grants.arguments_hash({"b": 2, "a": 1})
