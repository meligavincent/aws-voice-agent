"""AWS Lambda entry points. Logs contain metrics, never transcripts, codes or claim IDs."""

import json
import time
from functools import lru_cache

import boto3
from boto3.dynamodb.types import TypeDeserializer

from voice_agent.ai import PublicFAQ
from voice_agent.config import Settings
from voice_agent.service import TEXT, Agent, response
from voice_agent.store import Store


@lru_cache(maxsize=1)
def dependencies():
    settings = Settings.from_env()
    session = boto3.Session(region_name=settings.region)
    store = Store(session.resource("dynamodb"), settings.table, settings.region)
    return settings, session, store, Agent(store, PublicFAQ(session, settings))


def emit(name, value, unit="Count"):
    print(
        json.dumps(
            {
                "_aws": {
                    "Timestamp": int(time.time() * 1000),
                    "CloudWatchMetrics": [
                        {
                            "Namespace": "VoiceAgent",
                            "Dimensions": [[]],
                            "Metrics": [{"Name": name, "Unit": unit}],
                        }
                    ],
                },
                name: value,
            }
        )
    )


def lex(event, context):
    started = time.monotonic()
    try:
        _, _, _, agent = dependencies()
        result = agent.handle(event)
        emit("Handoff", int(result["sessionState"]["sessionAttributes"]["handoff"] == "true"))
        return result
    except Exception:
        emit("ApplicationFailure", 1)
        lang = "en" if event.get("bot", {}).get("localeId", "fr_FR").startswith("en") else "fr"
        return response(event, TEXT[lang]["handoff"], state="Failed", handoff=True)
    finally:
        emit("TurnLatency", (time.monotonic() - started) * 1000, "Milliseconds")


def publish(event, context):
    settings, session, store, _ = dependencies()
    sqs = session.client("sqs")
    failures = []
    deserializer = TypeDeserializer()
    for record in event.get("Records", []):
        try:
            if record.get("eventName") not in ("INSERT", "MODIFY"):
                continue
            item = {
                k: deserializer.deserialize(v)
                for k, v in record.get("dynamodb", {}).get("NewImage", {}).items()
            }
            if (
                item.get("kind") != "OUTBOX"
                or item.get("status") != "PENDING"
                or item.get("home_region") != settings.region
            ):
                continue
            if int(item["expires_at"]) <= int(store.clock()):
                emit("ExpiredOutbox", 1)
                continue
            sqs.send_message(
                QueueUrl=settings.queue_url,
                MessageBody=json.dumps({"operation_id": item["operation_id"]}),
            )
        except Exception:
            # DynamoDB Streams requires SequenceNumber, NOT eventID, for partial failures.
            failures.append({"itemIdentifier": record["dynamodb"]["SequenceNumber"]})
    return {"batchItemFailures": failures}


def worker(event, context):
    _, _, store, _ = dependencies()
    failures = []
    for record in event.get("Records", []):
        try:
            operation_id = json.loads(record["body"])["operation_id"]
            store.complete_callback(operation_id)
            emit("CallbackRecorded", 1)
        except Exception:
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
