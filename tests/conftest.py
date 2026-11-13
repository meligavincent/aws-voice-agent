import boto3
import pytest
from moto import mock_aws

from voice_agent.cli import seed
from voice_agent.store import Store


@pytest.fixture
def store(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("AWS_ENDPOINT_URL"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="eu-central-1")
        ddb.create_table(
            TableName="test",
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": k, "AttributeType": "S"} for k in ["pk", "gsi_pk", "gsi_sk"]
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "work",
                    "KeySchema": [
                        {"AttributeName": "gsi_pk", "KeyType": "HASH"},
                        {"AttributeName": "gsi_sk", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
        result = Store(ddb, "test", "eu-central-1", clock=lambda: 1800000000)
        seed(result)
        yield result
