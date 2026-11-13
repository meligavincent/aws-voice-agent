"""DynamoDB persistence: conditional writes, authentication limits and durable outbox."""

import hashlib
import hmac
import secrets
import time

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError


def hash_code(code: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", code.encode(), bytes.fromhex(salt), 210_000)
    return f"{salt}${digest.hex()}"


def verify_code(code: str, encoded: str) -> bool:
    try:
        salt, _ = encoded.split("$", 1)
        return hmac.compare_digest(hash_code(code, salt), encoded)
    except (ValueError, TypeError):
        return False


# Same expensive hash path when a claim does not exist. Never log an access code.
DUMMY_HASH = hash_code("not-a-real-code", "00" * 16)


class Store:
    def __init__(self, dynamodb, table: str, region: str, clock=time.time):
        self.table = dynamodb.Table(table)
        self.region = region
        self.clock = clock

    def get(self, pk):
        return self.table.get_item(Key={"pk": pk}, ConsistentRead=True).get("Item")

    def authenticate(self, claim_id: str, code: str) -> dict | None:
        """Limit ALL guesses per claim, including guesses from new sessions (15-minute windows)."""
        now = int(self.clock())
        window = now // 900
        limit_key = f"AUTH#{claim_id}#{window}"
        try:
            self.table.update_item(
                Key={"pk": limit_key},
                UpdateExpression="SET attempts = if_not_exists(attempts, :zero) + :one, expires_at = :ttl",
                ConditionExpression="attribute_not_exists(attempts) OR attempts < :limit",
                ExpressionAttributeValues={":zero": 0, ":one": 1, ":limit": 12, ":ttl": now + 1800},
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise
        claim = self.get(f"CLAIM#{claim_id}")
        ok = verify_code(code, claim.get("access_hash", DUMMY_HASH) if claim else DUMMY_HASH)
        return claim if claim and ok else None

    def create_callback(self, session_id: str, claim: dict) -> str:
        """One callback per claim/session; no external effect happens before this durable write."""
        operation_id = hashlib.sha256(f"callback:{session_id}:{claim['pk']}".encode()).hexdigest()
        now = int(self.clock())
        item = {
            "pk": f"OUTBOX#{operation_id}",
            "kind": "OUTBOX",
            "status": "PENDING",
            "operation_id": operation_id,
            "claim_pk": claim["pk"],
            "home_region": self.region,
            "created_at": now,
            "expires_at": now + 7 * 86400,
            "gsi_pk": f"OUTBOX#{self.region}",
            "gsi_sk": f"PENDING#{now:012d}#{operation_id}",
        }
        try:
            self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
        return operation_id

    def complete_callback(self, operation_id: str):
        """The implemented business effect is a durable callback ticket, NOT an outbound call."""
        outbox = self.get(f"OUTBOX#{operation_id}")
        if not outbox or outbox.get("kind") != "OUTBOX":
            raise ValueError("Unknown operation")
        if int(outbox["expires_at"]) <= int(self.clock()):
            raise ValueError("Expired operation requires operator review")
        if outbox["home_region"] != self.region:
            raise ValueError("Operation belongs to another region; reconcile ownership first")
        task = {
            "pk": f"TASK#{operation_id}",
            "kind": "CALLBACK",
            "status": "OPEN",
            "claim_pk": outbox["claim_pk"],
            "operation_id": operation_id,
            "created_at": outbox["created_at"],
            "expires_at": outbox["expires_at"],
        }
        try:
            self.table.put_item(Item=task, ConditionExpression="attribute_not_exists(pk)")
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
        # Crash between the two writes is safe: a retry sees the same TASK key.
        self.table.update_item(
            Key={"pk": outbox["pk"]},
            UpdateExpression="SET #s = :done REMOVE gsi_pk, gsi_sk",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":done": "DONE"},
        )
        return task

    def pending(self):
        """Paginated query for reconciliation; no table scan in the normal path."""
        kwargs = {
            "IndexName": "work",
            "KeyConditionExpression": Key("gsi_pk").eq(f"OUTBOX#{self.region}")
            & Key("gsi_sk").begins_with("PENDING#"),
        }
        while True:
            response = self.table.query(**kwargs)
            yield from response.get("Items", [])
            if "LastEvaluatedKey" not in response:
                break
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
