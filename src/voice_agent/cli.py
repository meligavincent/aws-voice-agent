"""Explicit local demo and operator tooling. AWS writes require an account match."""

import argparse
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from voice_agent.store import Store, hash_code


def event(name="ClaimStatus", code="654321", confirmation="None", session=None, locale="fr_FR"):
    return {
        "sessionId": session or str(uuid.uuid4()),
        "invocationSource": "FulfillmentCodeHook",
        "inputTranscript": "suivre mon dossier",
        "bot": {"localeId": locale},
        "sessionState": {
            "intent": {
                "name": name,
                "confirmationState": confirmation,
                "slots": {
                    "ClaimNumber": {"value": {"interpretedValue": "123456"}},
                    "AccessCode": {"value": {"interpretedValue": code}},
                },
            }
        },
    }


def seed(store):
    """Only fictitious data. Never overwrite a pre-existing claim."""
    item = {
        "pk": "CLAIM#123456",
        "kind": "DEMO_CLAIM",
        "access_hash": hash_code("654321"),
        "fr": {
            "status": "en cours d’examen",
            "missing": "constat signé",
            "next_step": "transmettre le constat via votre espace client",
        },
        "en": {
            "status": "under review",
            "missing": "signed incident report",
            "next_step": "upload the report through your customer portal",
        },
    }
    try:
        store.table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    except ClientError as error:
        if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise


def outputs(directory):
    result = subprocess.run(
        ["terraform", f"-chdir={directory}", "output", "-json"],
        check=True,
        capture_output=True,
        text=True,
    )
    return {key: value["value"] for key, value in json.loads(result.stdout).items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["seed", "demo", "reconcile", "ingest", "preflight"])
    parser.add_argument("--target", choices=["local", "aws"], default="local")
    parser.add_argument("--region", default="eu-central-1")
    parser.add_argument("--expected-account", help="Required for ALL real AWS operations")
    parser.add_argument(
        "--apply", action="store_true", help="Publish pending outbox operations; default is dry-run"
    )
    parser.add_argument("--terraform-dir", default=None)
    args = parser.parse_args()
    if args.target == "local":
        os.environ.update(
            AWS_ACCESS_KEY_ID="test",
            AWS_SECRET_ACCESS_KEY="test",
            AWS_ENDPOINT_URL="http://localhost:4566",
            AWS_DEFAULT_REGION=args.region,
        )
        os.environ.pop("AWS_SESSION_TOKEN", None)
    else:
        if not args.expected_account or len(args.expected_account) != 12:
            parser.error("AWS operations require --expected-account <12-digit-account>")
        if any(k.startswith("AWS_ENDPOINT_URL") for k in os.environ):
            parser.error("Unset local endpoint overrides before using real AWS")
    session = boto3.Session(region_name=args.region)
    identity = session.client("sts").get_caller_identity()
    if args.target == "aws" and identity["Account"] != args.expected_account:
        parser.error("AWS account mismatch")
    if args.command == "preflight":
        print(
            json.dumps(
                {"account": identity["Account"], "region": args.region, "identity_verified": True}
            )
        )
        return
    values = outputs(args.terraform_dir or f"infra/{'local' if args.target == 'local' else 'aws'}")
    regional = values if args.target == "local" else values["regions"][args.region]
    store = Store(session.resource("dynamodb"), values["table_name"], args.region)
    if args.command == "seed":
        seed(store)
        print(
            "Fictitious claim 123456 seeded if absent. Demo code: 654321. Never use this account for real data."
        )
    elif args.command == "demo":
        if args.target != "local":
            parser.error("demo is local-only; use scripts/smoke_aws.py for AWS")
        seed(store)
        client = session.client("lambda")
        session_id = str(uuid.uuid4())
        for name, confirmation in [
            ("ClaimStatus", "None"),
            ("RequestCallback", "None"),
            ("RequestCallback", "Confirmed"),
        ]:
            payload = event(name, confirmation=confirmation, session=session_id)
            result = client.invoke(
                FunctionName=regional["agent_function"], Payload=json.dumps(payload).encode()
            )
            body = json.load(result["Payload"])
            if result.get("FunctionError"):
                raise RuntimeError(body)
            print(body["messages"][0]["content"])
            if body["sessionState"]["sessionAttributes"]["handoff"] == "true":
                raise RuntimeError(
                    "Unexpected handoff; inspect aggregate metrics or reset local demo auth window"
                )
        operation = store.create_callback(session_id, store.get("CLAIM#123456"))
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            ticket = store.get(f"TASK#{operation}")
            if ticket:
                print(
                    "PASS: Lambda → DynamoDB outbox → Streams → Lambda → SQS → Lambda → one callback ticket"
                )
                return
            time.sleep(2)
        raise TimeoutError(
            "Callback ticket not observed; run reconcile --apply and inspect LocalStack logs"
        )
    elif args.command == "reconcile":
        sqs = session.client("sqs")
        count = expired = 0
        for item in store.pending():
            if int(item["expires_at"]) <= int(time.time()):
                expired += 1
                continue
            if args.apply:
                sqs.send_message(
                    QueueUrl=regional["queue_url"],
                    MessageBody=json.dumps({"operation_id": item["operation_id"]}),
                )
            count += 1
        print(
            json.dumps(
                {"eligible": count, "expired_require_review": expired, "published": args.apply}
            )
        )
    elif args.command == "ingest":
        if args.target != "aws" or not regional.get("knowledge_base_id"):
            parser.error("ingest requires AWS with RAG enabled")
        s3 = session.client("s3")
        for file in Path("examples/public-faq").glob("*.txt"):
            s3.upload_file(str(file), regional["documents_bucket"], f"public/{file.name}")
        client = session.client("bedrock-agent")
        job = client.start_ingestion_job(
            knowledgeBaseId=regional["knowledge_base_id"], dataSourceId=regional["data_source_id"]
        )["ingestionJob"]
        print(
            json.dumps(
                {
                    "ingestion_job": job["ingestionJobId"],
                    "status": job["status"],
                    "note": "Wait for COMPLETE before smoke tests; see AWS deployment guide",
                }
            )
        )


if __name__ == "__main__":
    main()
