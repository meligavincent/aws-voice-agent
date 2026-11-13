import json
from unittest.mock import Mock

import pytest
from boto3.dynamodb.types import TypeSerializer

from voice_agent import handlers
from voice_agent.config import Settings
from voice_agent.store import hash_code, verify_code


def test_crash_after_ticket_write_is_recoverable(store, monkeypatch):
    operation = store.create_callback("session", store.get("CLAIM#123456"))
    original = store.table.update_item
    monkeypatch.setattr(store.table, "update_item", Mock(side_effect=TimeoutError))
    with pytest.raises(TimeoutError):
        store.complete_callback(operation)
    assert store.get(f"TASK#{operation}")
    monkeypatch.setattr(store.table, "update_item", original)
    store.complete_callback(operation)
    assert store.get(f"OUTBOX#{operation}")["status"] == "DONE"
    assert sum(i["pk"].startswith("TASK#") for i in store.table.scan()["Items"]) == 1


def test_standby_worker_cannot_process_primary_work(store):
    operation = store.create_callback("session", store.get("CLAIM#123456"))
    store.region = "eu-west-2"
    with pytest.raises(ValueError, match="another region"):
        store.complete_callback(operation)
    assert store.get(f"TASK#{operation}") is None


def test_expired_work_requires_manual_review(store):
    operation = store.create_callback("session", store.get("CLAIM#123456"))
    store.clock = lambda: 1900000000
    with pytest.raises(ValueError, match="Expired"):
        store.complete_callback(operation)


def test_stream_partial_failure_uses_sequence_number_not_event_id(store, monkeypatch):
    operation = store.create_callback("session", store.get("CLAIM#123456"))
    serialize = TypeSerializer().serialize
    record = {
        "eventName": "INSERT",
        "eventID": "wrong-id",
        "dynamodb": {
            "SequenceNumber": "correct-sequence",
            "NewImage": {k: serialize(v) for k, v in store.get(f"OUTBOX#{operation}").items()},
        },
    }
    session = Mock()
    session.client.return_value.send_message.side_effect = TimeoutError
    monkeypatch.setattr(handlers, "dependencies", lambda: (Settings(), session, store, None))
    assert handlers.publish({"Records": [record]}, None) == {
        "batchItemFailures": [{"itemIdentifier": "correct-sequence"}]
    }


def test_partial_sqs_batch_does_not_replay_successful_record(store, monkeypatch):
    operation = store.create_callback("session", store.get("CLAIM#123456"))
    monkeypatch.setattr(handlers, "dependencies", lambda: (None, None, store, None))
    batch = {
        "Records": [
            {"messageId": "good", "body": json.dumps({"operation_id": operation})},
            {"messageId": "bad", "body": "invalid-json"},
        ]
    }
    assert handlers.worker(batch, None) == {"batchItemFailures": [{"itemIdentifier": "bad"}]}
    assert store.get(f"TASK#{operation}")


def test_handler_logs_no_transcript_or_credentials(monkeypatch, capsys):
    monkeypatch.setattr(
        handlers, "dependencies", Mock(side_effect=RuntimeError("secret-code-123456"))
    )
    result = handlers.lex(
        {"inputTranscript": "private text", "sessionState": {"intent": {"name": "FallbackIntent"}}},
        None,
    )
    logged = capsys.readouterr().out
    assert "123456" not in logged and "private text" not in logged
    assert "ApplicationFailure" in logged
    assert result["sessionState"]["sessionAttributes"]["handoff"] == "true"


def test_stub_is_rejected_in_aws(monkeypatch):
    monkeypatch.setenv("APP_ENV", "aws")
    monkeypatch.setenv("AI_MODE", "stub")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_access_hash_is_salted_and_verifiable():
    first, second = hash_code("123456"), hash_code("123456")
    assert first != second
    assert verify_code("123456", first)
    assert not verify_code("654321", first)
    assert not verify_code("123456", "invalid")
