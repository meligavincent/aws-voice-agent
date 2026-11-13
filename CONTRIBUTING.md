# Contributing

Use Python 3.12 and `uv sync --frozen`. Keep changes focused and run `make check validate`, `terraform -chdir=infra/aws test` and the LocalStack integration test when behavior/infrastructure changes. Do not add real customer examples.

Update `scripts/build_voice_templates.py`, then regenerate the bot JSON, rather than hand-editing the generated template. Update the conversation fixtures when changing intentional behavior. Changes to the model, prompt, guardrail or retrieval need the evaluation protocol in `docs/evaluation.md` as well as deterministic tests.

Never commit Terraform state, real tfvars, plans, credentials or raw AWS/contact logs. Document limitations and evidence instead of marking an untested cloud path as production-ready.
