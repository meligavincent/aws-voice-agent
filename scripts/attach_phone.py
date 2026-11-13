"""Associate an already-claimed phone number with this project's inbound flow."""

import argparse
import os

import boto3

from voice_agent.cli import outputs

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--expected-account", required=True)
parser.add_argument("--region", default="eu-central-1")
parser.add_argument("--phone-number-id", required=True)
args = parser.parse_args()
if any(k.startswith("AWS_ENDPOINT_URL") for k in os.environ):
    parser.error("Remove local endpoint overrides")
session = boto3.Session(region_name=args.region)
if session.client("sts").get_caller_identity()["Account"] != args.expected_account:
    parser.error("Account mismatch")
regional = outputs("infra/aws")["regions"][args.region]
session.client("connect").associate_phone_number_contact_flow(
    PhoneNumberId=args.phone_number_id,
    InstanceId=regional["connect_instance_id"],
    ContactFlowId=regional["contact_flow_id"],
)
print("Phone number associated with inbound contact flow.")
