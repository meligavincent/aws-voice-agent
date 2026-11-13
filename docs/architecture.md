# Architecture and boundaries

## Synchronous request path

Connect accepts the call, sets a French voice and the matching language attribute, and invokes the Lex V2 alias. Lex handles speech recognition, slot elicitation and callback confirmation. Polly synthesizes replies. Lambda implements a bounded router; it does not run an autonomous tool loop.

Claim status is an authenticated deterministic read. The demonstration credential is hashed with PBKDF2-SHA256 and a unique salt. A conditional DynamoDB counter limits all attempts for a claim in a 15-minute window, even when a caller changes session IDs. Unknown claims execute a dummy hash and receive the same public denial.

Public FAQ requests use a regional Bedrock Knowledge Base with S3 documents and OpenSearch Serverless. Retrieval is limited to three passages of at most 1,800 characters each. Generation is capped at 250 tokens, at temperature zero, with a published Bedrock guardrail. The retrieval-score threshold is an initial heuristic; it is not a calibrated confidence probability. Failed retrieval, a guardrail intervention or an unavailable dependency produces a handoff. The model must return a strictly validated answer/handoff JSON envelope; abstention, invalid output or truncation also triggers actual advisor routing instead of merely saying an advisor is needed. A warm-process circuit breaker opens after three failures for 30 seconds; it is not a shared distributed breaker.

SDK network connect/read timeouts are 1/3 seconds for Bedrock with no automatic request retry. Lambda has a 12-second hard limit, while SDK/application deadlines are best-effort latency controls rather than a guaranteed end-to-end deadline. Cold starts and retrieval/model latency must be measured in AWS. There is no streaming speech-to-speech or barge-in claim beyond the behavior provided by Connect/Lex.

## Durable callback path

The confirmation turn writes `OUTBOX#sha256(session,claim)` conditionally. The key is stable across delivery retries. DynamoDB Streams invokes a publisher, which sends only the operation ID to SQS. A worker reads the authoritative outbox, conditionally inserts `TASK#operation`, and marks the outbox `DONE`.

The task key prevents duplicates after a crash between those two writes. This is at-least-once delivery plus an idempotent internal effect, not globally exactly-once execution. A new conversation can intentionally create another callback request for the same claim. An external CRM/call adapter must implement its own idempotency and reconciliation contract before replacing this effect.

The stream filter and runtime check both constrain `kind=OUTBOX`, `status=PENDING` and `home_region=current`. Success removes the work-index keys. Failed stream records are reported by sequence number; failed SQS messages by message ID. Retries, age limits and a dead-letter queue bound background recovery. The outbox survives queue delivery failure, allowing operator reconciliation via a paginated GSI query.

## Regional behavior

Managed regional services provide the baseline availability architecture; no Kubernetes cluster, NAT gateway or customer-managed server is required. The optional standby duplicates regional functions, queues, voice resources, guardrail and RAG resources. DynamoDB Global Tables uses asynchronous replication, not a cross-region transaction lock. S3 replicates new `public/` objects; each region ingests its own vector index.

A `home_region` marker prevents normal replica stream events from executing the same callback in both regions. It does not solve split brain. The recovery runbook requires fencing the former writer and workers before a conditional ownership change. During a full region outage, unreconciled writes may not have replicated. No zero-loss or uninterrupted-call guarantee is made.

## Data model

| Key | Purpose | Retention |
|---|---|---|
| `CLAIM#id` | Fictitious source record, salted access hash and bilingual status fields | Until explicitly removed; production source integration is separate |
| `AUTH#id#window` | Per-claim authentication attempt counter | TTL 30 minutes; enforced 15-minute windows |
| `OUTBOX#operation` | Durable callback intent, status and owning region | TTL seven days; worker rejects already-expired work |
| `TASK#operation` | Internal callback ticket | TTL seven days; no claim about CRM retention |

TTL deletion is asynchronous. Work remains logically expired even if DynamoDB has not physically deleted it. The GSI uses `gsi_pk=OUTBOX#region` and time-ordered `gsi_sk=PENDING#timestamp#operation`. No table scan is used in the normal reconciliation path.

## Diagram-to-code mapping

The [animated design](assets/target-architecture.gif) predates this implementation. It is a **target blueprint**, not a deployment-status image.

| Design element | Repository implementation |
|---|---|
| Connect, Lex V2, Polly, Lambda | Terraform + native CloudFormation bot; French inbound flow, bilingual Lex locales |
| Bedrock, guardrails, Knowledge Base, S3, OpenSearch | Provisioned when RAG is enabled; requires AWS invocation/ingestion validation |
| DynamoDB, outbox, Streams, SQS, worker, DLQ | Implemented and core path exercised on LocalStack |
| Two regions / Global Tables / S3 CRR | Optional Terraform configuration; mocked plans checked, actual replication not yet exercised |
| Connect Global Resiliency / “standby ready and tested” | AWS onboarding and acceptance requirement, **not an achieved state of this repository** |
| DTMF fallback menu | Not included; current fallback is advisor routing/unavailable message |
| CodeCommit / CodeBuild / CodePipeline lane | Target AWS-native option; repository implements GitHub Actions verification and reviewed CLI Terraform deployment |
| Circuit breaker / retries | Per-process Bedrock breaker; async Lambda/SQS retries. No automatic Bedrock request retry or distributed breaker |
| CloudTrail | One multi-region management-event trail; not full data-plane auditing |
| Sessions in DynamoDB | Authentication counters and action state only; Lex owns dialogue session state |

See the README Mermaid diagram for the actual implemented service path.
