# Local development

## What runs

The Compose file pins LocalStack Community 4.14.0 by digest. It starts a dedicated service with a 1.5 GiB memory cap and two CPUs. Lambda execution adds separate Docker containers; allow additional memory. Docker socket access is required for those runtimes. Use an isolated development machine or CI runner; this is not a production deployment arrangement.

`infra/local` deploys the regional core: DynamoDB with a stream and work index, three Python Lambda functions and live aliases, stream/SQS event mappings, work and dead-letter queues, IAM execution roles, KMS and a versioned S3 document bucket. The same business handlers and core Terraform module are used by AWS.

| Capability | Local coverage |
|---|---|
| Claim authentication and private status | Actual Lambda invocation against LocalStack DynamoDB |
| Confirmation and duplicate callback | Actual Lambda invocation; one deterministic outbox/ticket key |
| Stream → publisher → SQS → worker | Actual event mappings and Docker Lambda runtimes |
| Partial writes and partial batches | Unit tests with injected failures; not a regional outage simulation |
| Lex voice / Polly / Connect | CloudFormation schema and flow-contract checks only |
| Bedrock model, guardrail and RAG quality | Unit tests with controlled responses; local FAQ stub |
| IAM, KMS security and TLS enforcement | Resources configured; emulator is not an enforcement audit |
| CloudWatch alarms | AWS only: the pinned emulator's DescribeAlarms serialization is incompatible with the current provider |
| Global Tables / S3 cross-region replication | Terraform mocked plans; real propagation and recovery untested |

No local test may be described as a telephone or production availability test.

## Commands

`make setup` installs the `uv.lock` versions. `make package` builds a ZIP containing the application and locked boto3 dependencies; test tools are excluded. `make local-apply` applies only `infra/local`, with hard-coded dummy credentials and localhost endpoints. `voice-agent` defaults to local mode and configures endpoints inside its own process; it does not edit your AWS profile.

`make integration` is explicitly gated by `RUN_LOCALSTACK_TESTS=1`. Ordinary `pytest` skips it. The integration test removes only the fictitious claim's current authentication counter so repeated test runs remain deterministic.

The demo command also needs available authentication attempts; after repeated manual runs, wait for the 15-minute window or reset the local environment. Never reset an AWS authentication counter to bypass a legitimate lockout.

## Reset and troubleshooting

The local service is ephemeral. `make local-down` removes the project containers, not any unrelated Docker services. Recreate with `make local-up local-apply`; Terraform refresh normally observes deleted resources and recreates them. Keep local Terraform state out of Git.

If local initialization was interrupted and Terraform reports an orphaned resource, inspect the dedicated Compose service and local state before resetting. Do not run a blanket `docker system prune` or delete another project's state.

- Docker Desktop context unavailable: use `docker --context default info` and `DOCKER_CONTEXT=default`.
- Port 4566 busy: inspect the existing listener; the project does not take it over automatically.
- Lambda image pull fails: verify Docker network access to the Lambda runtime image registry.
- Callback never completes: inspect `docker --context default compose logs --tail 100`; run `uv run voice-agent reconcile`, then `--apply` if appropriate. Do not infer success from the first acknowledgement alone.
- FAQ returns a canned answer locally: expected; `AI_MODE=stub` is allowed only with `APP_ENV=local`.
- Provider deprecation warning for DynamoDB `hash_key`/`range_key`: the pinned AWS provider still accepts these fields. This is not a failed validation; migrate when its supported replacement schema is available.

LocalStack 4.14.0 is a reproducibility choice, not a claim that it is the latest release. Review upgrades against this suite and update the image digest intentionally.
