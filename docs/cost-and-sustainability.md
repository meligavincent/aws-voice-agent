# Cost and sustainability

The design reduces unnecessary work in concrete ways: simple status/callback requests bypass the LLM, generation is bounded, only public FAQ content is indexed, application compute is on-demand, and ephemeral records/log history have explicit retention. There is no idle Kubernetes cluster or NAT gateway. These are design choices, not measured carbon or cost savings.

## Main cost drivers

| Service | Driver / trade-off |
|---|---|
| Connect and phone numbers | Number rental, telephony usage and contact-service features; check the country and region |
| Lex / Polly | Speech/text requests and synthesis; voice engine affects billing |
| Bedrock | Model input/output, guardrail processing and embedding ingestion |
| OpenSearch Serverless | Baseline capacity as well as use; replicas are enabled for resilience, so a quiet demo can still cost money |
| DynamoDB | On-demand reads/writes, storage, PITR and replication when standby is enabled |
| Lambda / SQS | Requests, duration, polling, retries and queue traffic |
| S3 / KMS / CloudTrail | Storage, versions, API requests, keys and audit storage |
| Second region | Another regional stack, index capacity, replication and operational work |

One region is the default to avoid provisioning a second RAG cluster for every portfolio demonstration. That choice sacrifices regional disaster recovery until the option is explicitly enabled and tested. High availability within regional managed services and recovery from a complete regional failure are different requirements.

Do not quote a monthly price from this repository. Build an estimate with current regional usage assumptions in the [AWS Pricing Calculator](https://calculator.aws/) and the relevant service pricing pages. Attach an AWS Budget and alert destination in your account before leaving a demonstration deployed. Budgets are account-specific and are not provisioned by this module.

## Tune using measurements

Measure model latency and answer quality before changing model size. Tune retrieval passage count and token budget against the approved corpus. Measure Lambda memory/duration and cold starts rather than adding provisioned concurrency by default. Monitor duplicate/retry volume; fixing a failing dependency is more efficient than scaling consumers that repeatedly fail.

Review current document versions, stale vector entries, failed ingestion and replication status. The source bucket's noncurrent-version lifecycle does not remove obsolete current documents from a vector index without the relevant deletion/ingestion workflow. Enforce the lifecycle in both regions.

The architecture follows the intent of the [AWS Well-Architected Sustainability Pillar](https://docs.aws.amazon.com/wellarchitected/latest/sustainability-pillar/welcome.html): avoid unnecessary processing and align capacity/retention with need. No environmental benefit is asserted without measurement.
