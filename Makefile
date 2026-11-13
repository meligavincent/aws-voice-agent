SHELL := /bin/bash
DOCKER_CONTEXT ?= default
UV ?= uv
.PHONY: setup check test package local-up local-apply demo integration local-down validate
setup:
	$(UV) sync --frozen
package:
	$(UV) run python scripts/package.py
check:
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run cfn-lint infra/modules/regional/templates/*.json
	terraform fmt -check -recursive infra
	$(UV) run pytest -m 'not integration' --cov=voice_agent --cov-report=term-missing
validate: package
	@for dir in local aws bootstrap; do terraform -chdir=infra/$$dir init -backend=false -input=false && terraform -chdir=infra/$$dir validate || exit 1; done
local-up:
	docker --context $(DOCKER_CONTEXT) compose up -d --wait
local-apply: package
	terraform -chdir=infra/local init -input=false
	terraform -chdir=infra/local apply -auto-approve -input=false
demo:
	$(UV) run voice-agent demo
integration:
	RUN_LOCALSTACK_TESTS=1 $(UV) run pytest -m integration -v
local-down:
	docker --context $(DOCKER_CONTEXT) compose down
