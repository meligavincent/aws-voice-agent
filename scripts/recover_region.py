"""Operator-driven outbox takeover after the former writer/worker has been fenced.
Global Tables uses eventual replication: this command CANNOT provide a global lock.
"""

import argparse
import json
import os
import time

import boto3
from botocore.exceptions import ClientError

from voice_agent.cli import outputs
from voice_agent.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-account", required=True)
    parser.add_argument("--from-region", required=True)
    parser.add_argument("--to-region", required=True)
    parser.add_argument("--source-fenced", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.source_fenced:
        parser.error(
            "Fence former intake AND workers; then explicitly attest --source-fenced. See docs/operations.md."
        )
    if args.from_region == args.to_region or any(
        k.startswith("AWS_ENDPOINT_URL") for k in os.environ
    ):
        parser.error("Distinct AWS regions and no endpoint overrides are required")
    session = boto3.Session(region_name=args.to_region)
    if session.client("sts").get_caller_identity()["Account"] != args.expected_account:
        parser.error("Account mismatch")
    config = outputs("infra/aws")
    target = config["regions"][args.to_region]
    store = Store(session.resource("dynamodb"), config["table_name"], args.from_region)
    sqs = session.client("sqs")
    eligible = recovered = expired = conflicts = 0
    for item in store.pending():
        if int(item["expires_at"]) <= int(time.time()):
            expired += 1
            continue
        eligible += 1
        if not args.apply:
            continue
        try:
            store.table.update_item(
                Key={"pk": item["pk"]},
                UpdateExpression="SET home_region = :target, gsi_pk = :gsi",
                ConditionExpression="home_region = :source AND #status = :pending",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":target": args.to_region,
                    ":source": args.from_region,
                    ":gsi": f"OUTBOX#{args.to_region}",
                    ":pending": "PENDING",
                },
            )
            sqs.send_message(
                QueueUrl=target["queue_url"],
                MessageBody=json.dumps({"operation_id": item["operation_id"]}),
            )
            recovered += 1
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            conflicts += 1
    print(
        json.dumps(
            {
                "eligible": eligible,
                "recovered": recovered,
                "expired_require_review": expired,
                "conflicts": conflicts,
                "dry_run": not args.apply,
            }
        )
    )


if __name__ == "__main__":
    main()
