# Operations and recovery

## Observe behavior, not just Lambda exceptions

The agent emits Embedded Metric Format counters `ApplicationFailure`, `Handoff` and `TurnLatency`. The worker emits `CallbackRecorded` per successful processing attempt; duplicate deliveries can increment it again, so it is **not a count of unique business callbacks**. The publisher emits `ExpiredOutbox`. No transcript, access code or claim identifier is intentionally logged by application code.

AWS alarms cover Lambda errors, application failures, non-empty DLQ, work-queue age over 120 seconds and publisher stream lag over 60 seconds. Thresholds are starter settings, not measured SLOs. Metrics have no per-customer dimensions. Configure regional SNS topics in `alarm_actions` and verify subscriptions; an alarm without an action does not notify an operator. Review Lambda throttles, p95 turn latency and model errors during acceptance. Set business SLOs only after measuring representative calls.

| Symptom | Response |
|---|---|
| Bedrock failures or slow retrieval | Verify model access, quotas, knowledge ingestion and guardrail version. Confirm human route still works. Do not silently turn off guardrails. |
| Lookup fails closed | Check DynamoDB/IAM and the account's access-attempt counter policy. Never log the code to debug it. |
| Outbox remains pending | Inspect stream lag, event mapping state, publisher role and SQS. Reconcile pending records once the cause is fixed. |
| Work queue ages | Inspect worker throttles, permissions, payload validity and region ownership. |
| DLQ grows | Identify whether the entry is a failed stream invocation envelope or an SQS business message before replay. They are different formats. |
| Human transfer unavailable | Check hours, advisor presence, routing profile and queue capacity. The flow's unavailable message is intentional, not proof of successful assistance. |

## Reconcile durable work

Local dry run and replay:

```bash
uv run voice-agent reconcile
uv run voice-agent reconcile --apply
```

AWS dry run and replay:

```bash
uv run voice-agent reconcile --target aws --region eu-central-1 --expected-account YOUR_12_DIGIT_ACCOUNT
uv run voice-agent reconcile --target aws --region eu-central-1 --expected-account YOUR_12_DIGIT_ACCOUNT --apply
```

The tool queries the `work` GSI, skips expired records and republishes operation IDs. The index is eventually consistent: repeat after propagation when necessary. Every replay re-reads the outbox in the worker. Duplicate enqueueing is expected and the ticket key remains stable. Successfully completed work is no longer indexed.

Do not blindly redrive the shared DLQ into the work queue. Stream failure destinations contain invocation metadata; inspect those records and use the authoritative outbox to reconstruct operations. Native SQS redrive is appropriate only for validated worker messages after the underlying error is resolved. Never “fix” an expired or unknown operation by fabricating an outbox row.

DynamoDB Streams retention and the configured one-hour maximum record age are shorter than outbox retention. The durable record is the recovery source. An operational schedule must run the dry-run reconciliation check and alert on old pending work; automated periodic reconciliation is not included in this version.

## Regional recovery exercise

Prerequisites: a provisioned and accepted standby, current RAG content, working regional quotas and model access, advisor capacity, and a verified telephony routing mechanism. A second independent Connect instance does not share a telephone number automatically.

1. Declare the incident and identify the authoritative active region. Stop new intake to the old writer through the approved Connect traffic-distribution procedure.
2. Fence old application writes and background workers. Disable their event-source mappings and/or concurrency through the incident procedure. **If you cannot establish fencing, do not assume that a marker in an asynchronously replicated table prevents split brain.** Choose whether to defer work or accept a documented reconciliation risk.
3. Observe replication health, compare action/ticket state and record potentially missing operations. Global Tables MREC has no guaranteed zero-data-loss recovery in this design.
4. Check standby Lex, Lambda, Bedrock, document ingestion, queue and advisor transfer. Run the AWS smoke test with `--region eu-west-2` against fictitious data.
5. Inspect the proposed takeover:

```bash
uv run python scripts/recover_region.py \
  --expected-account YOUR_12_DIGIT_ACCOUNT \
  --from-region eu-central-1 --to-region eu-west-2
```

6. Once fencing and reconciliation are established, rerun with `--source-fenced --apply`. Each update is conditional on pending status and the old owner in the destination replica. This is a **regional** condition, not a global lock. The operator assertion cannot verify infrastructure fencing on its own.
7. Run normal reconciliation in the destination. An interruption after ownership change but before queue send is recoverable through the new region's GSI/stream. Route new calls only after the accepted readiness checks and monitor outcomes.
8. Before failback, fence the current writer, reconcile again and repeat the same controlled procedure. Never allow both regions to resume solely because their health checks are green.

Measure detection time, replication lag, ownership reconciliation time and new-call recovery time. Record observed RTO/RPO for the tested scenario. Existing calls may be interrupted. No automatic failover or target timing is claimed by this project.

## Rollback and state restoration

Lambda `live` aliases reference published versions. A normal rollback is to check out the previously approved commit, recreate its deterministic ZIP and apply a reviewed Terraform plan. Emergency alias changes must be reconciled back into Terraform; otherwise the next apply will undo them. Keep the bot schema and handler response contract compatible during rollback.

Do not roll back DynamoDB business data merely to undo a code release. PITR recovery creates a new table and requires a planned application cutover; Global Table replicas and stream mappings must be reviewed. S3 versioning supports public-document restoration, followed by ingestion in each region. A previous model/guardrail release must be evaluated before traffic returns to it.

TTL retention is seven days for demo tickets/outbox. Real operational retention must be aligned with the enterprise's business obligations before connecting real customers. This project does not prescribe a legal retention period.
