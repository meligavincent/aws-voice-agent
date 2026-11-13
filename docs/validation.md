# Validation record

Initial local validation: 2026-11-13. This is an engineering test record, not customer-impact evidence.

| Check | Observed result |
|---|---|
| Python unit and conversation-contract suite | 39 passed; integration test excluded from this run |
| Actual LocalStack Lambda integration | Passed with deployed Lambda aliases, DynamoDB Stream, SQS and worker |
| Repeated confirmed request | Same operation key and completed internal ticket observed |
| Human-readable CLI demo | Completed the claim → confirmation → callback-ticket scenario |
| Terraform local apply | Regional core created successfully; no real AWS account used |
| Terraform single/dual-region plans | Two mocked plan tests passed; this is not an AWS deployment |
| CloudFormation templates | Checked with cfn-lint against resource schemas |
| Ruff / Terraform formatting / Terraform validation | Automated quality gates; see current workflow result |
| Real Connect telephone call | Not run |
| Real Bedrock/RAG/guardrail quality | Not run |
| IAM enforcement, KMS isolation, notification delivery | Not validated by the emulator |
| Actual region loss / Connect Global Resiliency | Not run; no measured RTO/RPO |

The runtime SDK was vendored in the Lambda ZIP and the LocalStack test was rerun after that packaging change. LocalStack uses the pinned 4.14.0 image digest from Compose. CloudWatch alarm emulation was excluded after observing a DescribeAlarms serialization error with the provider; AWS definitions remain present.

The current [GitHub Actions runs](https://github.com/meligavincent/aws-voice-agent/actions/workflows/ci.yml) are the source of truth for later commits. Run the commands in the README to reproduce checks. No historical deployment, quantitative business benefit or production service level is implied by this record.
