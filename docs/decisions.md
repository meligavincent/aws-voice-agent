# Architecture decisions

## ADR 001 — Managed serverless services, no Kubernetes

**Decision:** use Connect/Lex/Polly, Lambda, DynamoDB and SQS, with an optional managed RAG stack. These services fit short turns and asynchronous work without a customer-managed scheduler.

**Consequence:** less infrastructure to operate, but provider-specific interfaces and regional quotas. Kubernetes would not remove telephony/model dependencies and adds operational work for this scope. “Cloud native” here means managed, event-driven and infrastructure-defined; it does not require containers for every production component.

## ADR 002 — Separate private deterministic actions from generation

**Decision:** claim state and callbacks never depend on a model's proposed tool call. Only public service questions use RAG and generation.

**Consequence:** a smaller attack surface and fewer model requests. The assistant cannot autonomously adjudicate a claim or improvise unsupported business workflows. Expansion requires explicit intents, authorization and tests.

## ADR 003 — Durable outbox before acknowledgement

**Decision:** persist a confirmed callback intent before returning success, then use Streams/SQS to process it. The worker's internal ticket key is derived from the operation ID.

**Consequence:** recoverability after delivery failure and duplicate-safe ticket writes. The acknowledgement means the request is recorded, not that a human has called. Replay and external CRM idempotency remain explicit operational concerns.

## ADR 004 — Active/passive, manual recovery

**Decision:** offer an optional second regional application with asynchronous data replication and a home-region marker. Require operator fencing and reconciliation for takeover.

**Consequence:** a smaller consistency problem than active/active, but no automatic or zero-loss failover promise. Connect Global Resiliency is a separate AWS eligibility and routing concern. Recovery must be rehearsed with real calls.

## ADR 005 — Native CloudFormation for Lex lifecycle and vector index

**Decision:** Terraform manages nested native AWS templates for bot build/version/alias and the OpenSearch index, instead of shell-based provisioners or a legacy Lex V1 association resource.

**Consequence:** reviewed declarative resources with CloudFormation schema checks, plus the operational need to inspect stack events and regional resource support. Static validation cannot replace a deployment test.

## ADR 006 — Honest local emulation

**Decision:** exercise the event-driven core in LocalStack and use explicit test doubles for AI. Omit unsupported local alarm emulation while retaining AWS alarms.

**Consequence:** a reproducible, credential-free demonstration and meaningful failure tests. Speech quality, IAM enforcement, Bedrock behavior and regional outages remain real-cloud acceptance work. The CI badge is not a production certification.
