# Security model

## Trust boundaries

Callers and retrieved passages are untrusted. Lex invokes one scoped Lambda alias; the model has no tool execution capability. The router owns private lookup and callback actions, and neither is selected by model-generated code or JSON. Only authenticated claim data is rendered into deterministic responses. Data read from the claim store is not inserted into the generative prompt.

The caller's FAQ utterance itself can still contain personal information. Guardrails do not make all input non-personal, and input must be processed by the relevant AWS services for checking/retrieval. Approve data handling, regional routing and service settings for the real enterprise before use. Only public, reviewed documents may enter the RAG bucket/index.

## Demo authentication is not enterprise identity

The six-digit fixture code is public and deliberately limited to fictitious data. Salted PBKDF2 hashes and a per-claim attempt counter demonstrate control flow; they are not a substitute for a trusted customer identity/OTP integration. The system has no OTP issuance, identity proofing, code-expiry/recovery or fraud-detection service.

The 12-attempt/15-minute fixed-window limit includes successful attempts and spans session IDs. It can be abused to deny service to a known claim identifier, and window boundaries permit bursts. MREC replication does not create a global atomic rate limit. Production must integrate the enterprise's verification service, define account-recovery behavior and control abuse at the telephony/customer-identity boundary. Do not populate real claims under the demo mechanism.

Lex keeps the code only as required during slot/confirmation handling. Fulfillment clears it from returned slots, and access-code slots are configured for obfuscation. Conversation logs and flow logs are not enabled by the created resources; existing Connect instances must be audited independently. The application does not configure recordings. A PIN spoken on a telephone call is not equivalent to a phishing-resistant authentication factor.

## Infrastructure controls

- Separate Lambda execution roles; agent accesses the claim table and approved Bedrock resources, publisher reads streams/sends queue messages, worker consumes messages/writes tickets.
- Service principals are used for trust. Lex invocation is scoped to the alias and account; Connect access to Lex is scoped to the instance/account.
- KMS rotation for regional document/queue keys; DynamoDB encryption at rest with AWS-managed keys, PITR and AWS deletion protection.
- S3 block-public-access, versioning, encrypted objects, TLS-only bucket policies on AWS, and bounded retention for old document versions.
- OpenSearch public network endpoint with IAM plus explicit data-access policies. This is not a private network. Public documents only; a VPC-only version requires a different deployment-runner/network design.
- CloudTrail management events in a private, versioned, encrypted bucket with integrity validation. Data-plane auditing, an organization trail, Security Hub/GuardDuty and compliance controls are not implied.
- S3 Terraform state uses encryption, versioning and native locking. Treat state/plan files as sensitive even when credentials are not stored in them.

Some AWS calls do not support a narrower resource ARN (for example Polly synthesis and stream enumeration). The relevant wildcard is limited to the necessary action; it is not an administrator policy. The provisioning principal necessarily has broader rights than runtime roles and must be governed separately.

## Retention and logging

Application logs retain 14 days. SQS retains ordinary work for four days and dead letters for 14 days. Demo outbox/tickets expire after seven days; auth counters have short TTLs. CloudTrail archive objects expire after 365 days and noncurrent versions after 30 days. Document current versions persist; noncurrent versions expire after 90 days. These defaults are engineering examples, not a regulatory claim.

Do not add raw event logging to Lambda or publish contact records as CI artifacts. Inspect metadata carefully when diagnosing AWS errors. The included integration fixtures contain no real personal information.

## Reporting a problem

Do not publish credentials, customer records or exploit payloads containing personal data in a public issue. Use the repository owner's GitHub contact route or GitHub private vulnerability reporting if enabled. For a leaked credential, revoke/rotate it first through the relevant account process; removing it from a Git commit is insufficient.
