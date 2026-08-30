"""state.py's whole job is atomic, conditional DynamoDB writes. Unit tests
replace the table with an in-memory fake that honors ConditionExpression
the same way real DynamoDB does (raises ClientError/ConditionalCheckFailedException),
so the idempotency/replay-prevention logic is exercised without a real table.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("APPROVAL_STATE_TABLE", "fake-table")

from botocore.exceptions import ClientError  # noqa: E402

import state  # noqa: E402


class _FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item, ConditionExpression=None):
        key = Item["reference_id"]
        if ConditionExpression == "attribute_not_exists(reference_id)" and key in self.items:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException", "Message": "exists"}}, "PutItem")
        self.items[key] = dict(Item)

    def get_item(self, Key):
        item = self.items.get(Key["reference_id"])
        return {"Item": item} if item is not None else {}

    def update_item(self, Key, UpdateExpression, ConditionExpression=None, ExpressionAttributeNames=None, ExpressionAttributeValues=None):
        key = Key["reference_id"]
        item = self.items.get(key)
        if ConditionExpression == "attribute_exists(reference_id) AND #status = :pending":
            if item is None or item.get("status") != ExpressionAttributeValues.get(":pending", "PENDING"):
                raise ClientError({"Error": {"Code": "ConditionalCheckFailedException", "Message": "not pending"}}, "UpdateItem")
        if ConditionExpression == "attribute_not_exists(#grant_consumed_at)":
            if item is None or "grant_consumed_at" in item:
                raise ClientError({"Error": {"Code": "ConditionalCheckFailedException", "Message": "already consumed"}}, "UpdateItem")
        if item is None:
            item = {"reference_id": key}
            self.items[key] = item
        if ":status" in (ExpressionAttributeValues or {}):
            item["status"] = ExpressionAttributeValues[":status"]
            item["decision"] = ExpressionAttributeValues[":decision"]
            item["decided_at"] = ExpressionAttributeValues[":decided_at"]
            for opt in ("approver", "instruction_text", "grant"):
                v = ExpressionAttributeValues.get(f":{opt}")
                if v is not None:
                    item[opt] = v
        if ":now" in (ExpressionAttributeValues or {}):
            item["grant_consumed_at"] = ExpressionAttributeValues[":now"]
        if ":grant" in (ExpressionAttributeValues or {}) and ExpressionAttributeValues.get(":grant") is not None and "grant" not in (item or {}):
            item["grant"] = ExpressionAttributeValues[":grant"]


def _patch_table(monkeypatch):
    fake = _FakeTable()
    monkeypatch.setattr(state, "_table", fake)
    return fake


def _record(**overrides):
    base = dict(
        kind="approval", tool_name="t", bare_tool_name="t", target="tgt", arguments_hash="h",
        correlation_id="c", requesting_principal=None, decision_mode="deterministic",
        human_question="q?", reason="r",
    )
    base.update(overrides)
    return base


def test_create_pending_then_get(monkeypatch):
    _patch_table(monkeypatch)
    state.create_pending("appr-1", **_record())
    record = state.get_record("appr-1")
    assert record["status"] == "PENDING"


def test_duplicate_create_pending_raises(monkeypatch):
    _patch_table(monkeypatch)
    state.create_pending("appr-1", **_record())
    try:
        state.create_pending("appr-1", **_record())
        assert False, "expected RecordExistsError"
    except state.RecordExistsError:
        pass


def test_get_missing_record_raises(monkeypatch):
    _patch_table(monkeypatch)
    try:
        state.get_record("does-not-exist")
        assert False, "expected RecordNotFoundError"
    except state.RecordNotFoundError:
        pass


def test_decide_once_then_second_decision_rejected(monkeypatch):
    _patch_table(monkeypatch)
    state.create_pending("appr-1", **_record())
    state.record_decision("appr-1", decision="deny")
    assert state.get_record("appr-1")["status"] == "DENIED"
    try:
        state.record_decision("appr-1", decision="approve")
        assert False, "expected AlreadyDecidedError (duplicate human response)"
    except state.AlreadyDecidedError:
        pass
    # Still DENIED -- the second, duplicate decision must not have overwritten it.
    assert state.get_record("appr-1")["status"] == "DENIED"


def test_grant_consumed_exactly_once(monkeypatch):
    _patch_table(monkeypatch)
    state.create_pending("appr-1", **_record())
    state.record_decision("appr-1", decision="approve", grant="signed-token")
    state.mark_grant_consumed("appr-1")
    try:
        state.mark_grant_consumed("appr-1")
        assert False, "expected GrantAlreadyConsumedError (replay)"
    except state.GrantAlreadyConsumedError:
        pass
