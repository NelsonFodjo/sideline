# python3 on most Linux and macOS; override with `make run PY=python`
PY ?= python3
export PYTHONPATH := .:tests

.PHONY: run test smoke sim clean lint aws-check create-table docker deploy verify-data env evidence

run:              ## start the MCP server against the recorded match
	$(PY) -m sideline

run-fast:         ## same, but the match runs 20x so you can see events land
	SIDELINE_REPLAY_SPEED=20 $(PY) -m sideline

test:             ## full suite, no network, no credentials
	@for t in tests/test_clean_clone.py tests/test_routing_phrases.py tests/test_language.py tests/test_agent.py \
	          tests/test_tools.py tests/test_what_did_i_miss.py \
	          tests/test_broadcast_sync.py tests/test_pronouns.py \
	          tests/test_envfile.py tests/test_autodetect.py tests/test_auth.py tests/test_aws_helpers.py \
	          tests/test_statsbomb.py tests/test_apifootball.py tests/test_simulator.py tests/test_summaries.py \
	          tests/test_mcp_protocol.py; do \
		echo "=== $$t"; SIDELINE_MODE=demo SIDELINE_BEDROCK=off $(PY) $$t || exit 1; \
	done
	@echo "\nall suites passed"

smoke:            ## exercise every tool against a running server
	$(PY) scripts/smoke_test.py

verify-aws:       ## check the AWS setup layer by layer
	$(PY) scripts/verify_aws.py

aws-check: verify-aws   ## alias

evidence:         ## measure the project's claims and rewrite docs/EVIDENCE.md
	$(PY) scripts/collect_evidence.py

env:              ## show which environment variables are set (never prints values)
	$(PY) scripts/env_status.py

verify-data:      ## check the live football feed key and quota
	$(PY) scripts/verify_provider.py

create-table:     ## create the DynamoDB table (or set SIDELINE_DYNAMO_ENDPOINT for local)
	$(PY) scripts/create_table.py

docker:           ## build the App Runner image locally
	docker build --platform linux/amd64 -t sideline .

deploy:           ## build, push to ECR, deploy the CloudFormation stack
	./scripts/deploy_aws.sh

sim:              ## open the voice simulator (served by the running server)
	@python3 -c "import webbrowser;webbrowser.open('http://127.0.0.1:8765/')" \
	  || echo "open http://127.0.0.1:8765/"

clean:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
