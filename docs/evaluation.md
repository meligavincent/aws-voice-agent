# Evaluation and LLMOps scope

This project fits **LLMOps / applied AI operations**: it versions a prompt, model configuration, guardrail, knowledge content, infrastructure and conversation policies. It does not train a model or implement a full training-oriented MLOps platform. There is no fabricated training dataset, model registry or customer-success metric.

## Deterministic quality gates

`evals/policy_cases.json` is a small reviewed behavior corpus covering French/English lookup, bad access, an explicit human request, private information in FAQ and dependency failure. Tests execute the actual router with controlled dependencies. Failure tests cover durable effects, duplicate delivery, partial batches, cross-region ownership and expiry. The LocalStack test exercises the deployed event-driven path.

These tests prove particular software properties. They **do not** measure speech recognition, model factuality, hallucination rate or real customer satisfaction. The retrieval score threshold of 0.35 is a starter heuristic, not an empirically established confidence level.

## Versioned release inputs

- Prompt and `PROMPT_VERSION` in `src/voice_agent/ai.py` (`faq-v1`). Change the version when meaning changes.
- Model/inference profile in Terraform variables; record the actual resolved AWS model/profile in private release evidence.
- Immutable published guardrail version in Lambda configuration.
- Approved S3 public-document versions and the completed ingestion-job ID in each region.
- Lex locale template, Lambda code ZIP hash, dependency locks and Git commit.

A model/guardrail/document change is an application change. It must pass deterministic checks plus a live evaluation appropriate to its impact. An evaluation should never silently disable guardrails to make an answer pass.

## Live evaluation protocol

After AWS ingestion completes, use fictitious data and a reviewed corpus covering:

| Category | Expected behavior |
|---|---|
| Public opening hours, upload instructions, callback process | Concise answer supported by the approved FAQ, matching language |
| Question absent from the documents | Clear uncertainty/human escalation; no invented procedure |
| Personal coverage/payment/liability decision | No decision or promise; advisor route |
| Prompt injection in caller text or a retrieved passage | No instruction override, secret disclosure or action execution |
| Email/phone/account information in a general question | Approved privacy handling and guardrail behavior |
| Timeout, access denial, empty retrieval, blocked generation | Handoff rather than a fabricated success |
| French/English, noisy audio, accents, digit strings | Correct intent/slot capture or safe re-prompt/handoff |

Score factual support, completeness, safe refusal, language match, speech intelligibility, confirmation correctness and successful transfer separately. Record p50/p95 latency, token use and cost from actual runs. Set pass thresholds before the experiment; include sample size, model version and failure examples in the private report. Review repeated trials because model output can vary even at temperature zero.

The shipped `scripts/smoke_aws.py` is an automated **Lex text + callback** smoke test. It deliberately does not pretend to be this live semantic/acoustic evaluation. A release needs both automation and representative voice/human-path testing.
