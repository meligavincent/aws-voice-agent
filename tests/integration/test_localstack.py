"""Actual Lambda Docker runtimes + LocalStack services, not Moto or in-process mocks."""

import json
import os
import time
import uuid

import boto3
import pytest

from voice_agent.cli import event, outputs, seed
from voice_agent.store import Store

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_LOCALSTACK_TESTS") != "1", reason="explicit LocalStack opt-in required"
    ),
]


def test_lambda_stream_queue_worker_roundtrip(monkeypatch):
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    session = boto3.Session(region_name="eu-central-1")
    assert session.client("sts").get_caller_identity()["Account"] == "000000000000"
    values = outputs("infra/local")
    store = Store(session.resource("dynamodb"), values["table_name"], "eu-central-1")
    seed(store)
    # Remove only this fixture's auth window so repeated local runs remain reproducible.
    store.table.delete_item(Key={"pk": f"AUTH#123456#{int(time.time()) // 900}"})
    client = session.client("lambda")
    session_id = str(uuid.uuid4())

    def invoke(request):
        result = client.invoke(
            FunctionName=values["agent_function"], Payload=json.dumps(request).encode()
        )
        body = json.load(result["Payload"])
        assert "FunctionError" not in result, body
        return body

    invalid = invoke(event(code="111111"))
    assert invalid["sessionState"]["sessionAttributes"]["handoff"] == "true"
    status = invoke(event())
    assert "constat signé" in status["messages"][0]["content"]
    pending = invoke(event("RequestCallback", session=session_id))
    assert pending["sessionState"]["dialogAction"]["type"] == "ConfirmIntent"
    request = event("RequestCallback", session=session_id, confirmation="Confirmed")
    for _ in range(2):
        confirmed = invoke(request)
        assert confirmed["sessionState"]["intent"]["state"] == "Fulfilled"
    import hashlib

    operation = hashlib.sha256(f"callback:{session_id}:CLAIM#123456".encode()).hexdigest()
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        outbox = store.get(f"OUTBOX#{operation}")
        if outbox and outbox["status"] == "DONE":
            break
        time.sleep(2)
    assert store.get(f"TASK#{operation}")["status"] == "OPEN"
    assert store.get(f"OUTBOX#{operation}")["status"] == "DONE"
    assert store.get(f"OUTBOX#{operation}").get("gsi_pk") is None
