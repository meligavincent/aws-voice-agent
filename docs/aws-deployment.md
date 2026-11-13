# Deploying the reference system to AWS

This guide provisions the application in your account. Its commands have **not** been executed against a real AWS account as part of the initial local validation. A successful Terraform apply is followed by runtime and telephone acceptance tests; it is not itself proof of production readiness.

## 1. Prepare the account

Use a dedicated development account and an AWS CLI v2 profile, preferably an IAM Identity Center session. Do not paste access keys into Terraform files, source code, GitHub or this public repository.

```bash
aws configure sso --profile voice-agent
aws sso login --profile voice-agent
export AWS_PROFILE=voice-agent
export AWS_REGION=eu-central-1
# Remove any endpoint/dummy-credential overrides from previous shell experiments.
unset AWS_ENDPOINT_URL AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
uv run voice-agent preflight --target aws --expected-account YOUR_12_DIGIT_ACCOUNT
```

`preflight` verifies the account identity, not every quota or permission. Terraform also restricts both providers with `allowed_account_ids`.

The deployment principal needs provisioning permissions for the services in the plan: IAM roles/policies and PassRole, Lambda, DynamoDB, SQS, S3, KMS, CloudWatch, CloudTrail, Connect, Lex V2, Bedrock Knowledge Bases/Guardrails, OpenSearch Serverless, CloudFormation and required service-linked roles. The Terraform role is separate from the tightly scoped runtime roles. Use an administrator-approved provisioning role with a permissions boundary appropriate to your organization; the repository does not grant itself administrator access.

For OpenSearch index creation, that principal must have IAM `aoss:APIAccessAll` for the new collection **as well as** the data-access policy created by Terraform. Provide the underlying IAM role ARN (including an IAM Identity Center role path when applicable), not the `arn:aws:sts:...:assumed-role/.../session` returned by STS. CloudFormation operates with that caller's permissions because this stack has no separate execution role.

Check the following in your selected regions:

- Connect, Lex V2 French/English, Polly voices, Bedrock model/guardrails/knowledge bases, and OpenSearch Serverless are available.
- Your chosen model supports the Converse API and your account can invoke it. For a cross-region inference profile, set its ARN in `model_id` and the underlying model ID in `foundation_model_id`. Review destination-region/data-residency implications and SCPs. Defaults are configuration examples, not an availability guarantee.
- Titan Text Embeddings V2 (`amazon.titan-embed-text-v2:0`) is invokable in each RAG region. The vector dimension is 1024.
- Lambda reserved-concurrency quotas support three functions at five concurrent executions each; Lex, Connect and Bedrock quotas fit your intended traffic.
- A phone number is available/claimable for your business and jurisdiction. Claiming/porting can require account validation and documents; Terraform cannot bypass that process.

References: [Bedrock supported models](https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html), [Connect quotas](https://docs.aws.amazon.com/connect/latest/adminguide/amazon-connect-service-limits.html), [OpenSearch Serverless access policies](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-data-access.html).

## 2. Bootstrap protected Terraform state

```bash
make setup package
terraform -chdir=infra/bootstrap init
terraform -chdir=infra/bootstrap plan -var='account_id=YOUR_12_DIGIT_ACCOUNT' -out=bootstrap.tfplan
terraform -chdir=infra/bootstrap apply bootstrap.tfplan
terraform -chdir=infra/bootstrap output state_bucket
cp infra/aws/backend.hcl.example infra/aws/backend.hcl
cp infra/aws/terraform.tfvars.example infra/aws/terraform.tfvars
```

Edit `backend.hcl` with the actual bucket output and region. Edit `terraform.tfvars` with your account and IAM deployment principal. The state bucket is private, versioned, encrypted and protected from destruction. Main state uses S3 native lockfiles; the bootstrap itself initially has local state, which must be stored securely and excluded from Git. Backend configuration and variable values are ignored by Git.

Default: one region, voice and RAG enabled. OpenSearch Serverless is a continuously billed resource; review the [cost guide](cost-and-sustainability.md) before apply. Setting `enable_rag=false` still allows claim lookup/callback, but FAQ requests hand off to an advisor. It must not be advertised as a working generative FAQ in that mode.

## 3. Validate, review and apply

```bash
make check validate
terraform -chdir=infra/aws init -reconfigure -backend-config=backend.hcl
terraform -chdir=infra/aws plan -out=deployment.tfplan
terraform -chdir=infra/aws apply deployment.tfplan
terraform -chdir=infra/aws output -json > artifacts/aws-outputs.json
```

Create `artifacts/` first if it does not exist. Plans and outputs can contain account/resource identifiers; keep them private. Keep the build ZIP corresponding to the approved plan. Never apply an older plan after changing that file.

The nested CloudFormation stacks exist to manage the Lex V2 build/version/alias lifecycle and the OpenSearch index with native AWS resources. There are no `local-exec` provisioning calls and no hidden credentials in templates. Lex aliases point at published Lambda aliases; code updates publish new Lambda versions. Bot locale changes change the generated version resource identifier.

S3 public-document buckets use KMS, block public access and reject plaintext transport. The OpenSearch network endpoint is public but requires IAM **and** its data-access policy; no anonymous access is granted. Only non-personal public FAQ documents belong there. A private-network variant would require VPC endpoint/deployment-runner design and is not silently claimed here.

If CloudFormation/index creation fails, inspect its stack events. New IAM/AOSS policies may take time to propagate; retry a reviewed apply after resolving the cause. Static schema validation cannot prove regional support for a newly available CloudFormation resource.

## 4. Load fictitious data and public knowledge

```bash
uv run voice-agent seed --target aws --expected-account YOUR_12_DIGIT_ACCOUNT
uv run voice-agent ingest --target aws --expected-account YOUR_12_DIGIT_ACCOUNT
```

The seed only inserts an absent fictitious claim and never replaces an existing record. Use a demo account: the sample access code is public. Replace the public FAQ files with approved content before a business release. `ingest` uploads only `examples/public-faq/*.txt` to `public/` and starts an ingestion job. Wait for the job to report `COMPLETE` in Bedrock before testing answers. A failed job must be investigated; upload success alone is insufficient.

If standby is enabled, S3 replication handles newly uploaded public objects. Wait for replication and start ingestion separately in the standby region; `voice-agent ingest --region eu-west-2` can explicitly upload the approved source files and trigger its job too. Objects created before replication was enabled need a backfill. Deletions are not automatically replicated; remove stale content in both buckets and ingest both indexes.

## 5. Set up the human path and phone number

Terraform creates a Connect instance unless an existing instance ID is supplied, a Lex bot, a French inbound flow and an advisor queue with Monday–Friday 09:00–17:00 Europe/Paris hours. Lex includes `fr_FR` and `en_GB`; the shipped phone flow sets `fr-FR`. English is available through Lex runtime; a bilingual phone selection menu is not included.

Before connecting a real number:

1. Create/sign in as an administrator for the Connect instance.
2. Create advisor users and a routing profile containing the Terraform-created advisor queue. Assign that profile, configure the agent workspace/CCP and set a test advisor Available. User identities and staffing are intentionally not baked into a public repository.
3. Review the queue's customer queue flow and configure a maximum-wait/overflow policy for your operation. The supplied inbound flow checks opening hours and queue-capacity errors; the default Connect queue behavior is not a staffing guarantee.
4. Claim or port an eligible phone number through Connect. No automatic purchase is made.
5. Associate the existing number with the deployed flow:

```bash
uv run python scripts/attach_phone.py \
  --expected-account YOUR_12_DIGIT_ACCOUNT \
  --region eu-central-1 \
  --phone-number-id YOUR_CONNECT_PHONE_NUMBER_ID
```

The flow uses a generic escalation reason, not a transcript or secret code, for the advisor. Detailed customer context requires an authenticated CRM/agent-workspace integration.

References: [Connect + Lex V2 setup](https://docs.aws.amazon.com/connect/latest/adminguide/amazon-lex.html), [language/voice configuration](https://docs.aws.amazon.com/connect/latest/adminguide/set-voice.html), [Lex flow action](https://docs.aws.amazon.com/connect/latest/devguide/participant-actions-connectparticipantwithlexbot.html).

## 6. Release acceptance

```bash
uv run python scripts/smoke_aws.py --expected-account YOUR_12_DIGIT_ACCOUNT --region eu-central-1
```

This invokes **real Lex text runtime**, validates the authenticated claim and confirms a callback through to its stored ticket. It writes only test actions against the fictitious fixture. It is not a speech test. Repeated runs are subject to the authentication attempt limit.

Then test a real telephone call:

- Successful claim lookup; spoken and DTMF digit recognition where supported; leading zeros, accents and noisy audio.
- Wrong/missing credentials and repeated attempts never reveal claim status.
- Declined callback creates no action; confirmation creates one ticket even after event retries.
- General FAQ is grounded in approved documents; unknown/unsafe questions hand off. Evaluate in both languages through the corresponding configured channel.
- Bedrock access denial/timeout leads to human routing, including a successful live advisor transfer.
- Closed hours, full queue and unavailable advisors have an approved customer outcome.
- Logs and contact attributes do not expose access codes or claim details; no conversation recording is enabled unintentionally.
- Regional alarms have a subscribed operational destination. Force a controlled failure and verify notification delivery.

Record results, resource versions and the tested commit privately. Do not publish caller information or real account state in this repository. See [evaluation](evaluation.md) for the model-specific checks.

## 7. Optional standby and Global Resiliency

Set `enable_standby=true` only after reviewing cost and [operations](operations.md). This creates a second regional application, Global Table replica and public-document replication. It does **not** create a Connect Global Resiliency pairing or move phone traffic.

AWS Global Resiliency has support-plan, identity, region-pair, quota and phone-number requirements. Frankfurt/London is a documented pair. Follow [AWS prerequisites](https://docs.aws.amazon.com/connect/latest/adminguide/connect-global-resiliency-requirements.html) and [setup](https://docs.aws.amazon.com/connect/latest/adminguide/get-started-connect-global-resiliency.html) with AWS support. Configure/import the resulting existing regional instance IDs; do not apply destructive replacement of independently created demo instances. Review how mirrored contact flows select region-local Lex aliases, and keep Lambda function names aligned. Existing instances may have logging settings outside this module; audit them explicitly.

A second healthy app is not proof of recoverable phone traffic. Complete a controlled exercise with routing, advisor capacity, model availability and outbox reconciliation. No RTO/RPO is asserted until measured; ongoing calls may be disrupted.

## Cleanup

Review `terraform plan -destroy` before applying it. DynamoDB deletion protection is enabled by default and must be deliberately changed before deletion. S3 buckets have versioning and do not force-delete on AWS: empty only the identified project buckets/versions after approved retention checks. Connect phone numbers and users may require cleanup before an instance can be deleted. Keep the protected state bucket and bootstrap state until teardown is complete. The local demo has no AWS bill; a deployed RAG stack does.
