"""Real AWS release check: Lex runtime text, claim lookup, confirmed action and async worker.
This is NOT a telephony/acoustic test. Requires explicit account match and fictitious seed data.
"""

import argparse
import hashlib
import os
import time
import uuid

import boto3

from voice_agent.cli import outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-account", required=True)
    parser.add_argument("--region", default="eu-central-1")
    args = parser.parse_args()
    if any(key.startswith("AWS_ENDPOINT_URL") for key in os.environ):
        parser.error("Remove endpoint overrides before real AWS smoke tests")
    session = boto3.Session(region_name=args.region)
    assert session.client("sts").get_caller_identity()["Account"] == args.expected_account, (
        "Account mismatch"
    )
    values = outputs("infra/aws")
    region = values["regions"][args.region]
    client = session.client("lexv2-runtime")
    for intent_name in ["ClaimStatus", "RequestCallback"]:
        session_id = "smoke-" + uuid.uuid4().hex
        requests = [
            "suivre mon dossier" if intent_name == "ClaimStatus" else "demander un rappel",
            "123456",
            "654321",
        ]
        if intent_name == "RequestCallback":
            requests.append("oui")
        for text in requests:
            result = client.recognize_text(
                botId=region["lex_bot_id"],
                botAliasId=region["lex_alias_id"],
                localeId="fr_FR",
                sessionId=session_id,
                text=text,
            )
        assert result["sessionState"]["intent"]["name"] == intent_name, result["sessionState"][
            "intent"
        ]["name"]
        assert result["sessionState"]["intent"]["state"] == "Fulfilled", "Intent failed"
        assert result["sessionState"].get("sessionAttributes", {}).get("handoff") == "false", (
            "Unexpected handoff"
        )
        if intent_name == "ClaimStatus":
            assert any(
                "constat signé" in m.get("content", "") for m in result.get("messages", [])
            ), "Wrong seeded claim response"
        else:
            operation = hashlib.sha256(f"callback:{session_id}:CLAIM#123456".encode()).hexdigest()
            table = session.resource("dynamodb").Table(values["table_name"])
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if table.get_item(Key={"pk": f"TASK#{operation}"}, ConsistentRead=True).get("Item"):
                    break
                time.sleep(2)
            else:
                raise TimeoutError("Callback worker did not create ticket")
        print(f"PASS {args.region}: {intent_name}")
    print(
        "Voice recognition, phone-number routing, advisor transfer and regional failover still require the manual acceptance tests in docs/aws-deployment.md."
    )


if __name__ == "__main__":
    main()
