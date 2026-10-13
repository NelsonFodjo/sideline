# python3 on most Linux and macOS; override with `make run PY=python`
PY ?= python3
export PYTHONPATH := .:tests

.PHONY: run sim test env verify-data aws-check create-table stt-check compare-stt clean

run:              ## start the server (needs SIDELINE_FOOTBALL_KEY; see README)
	$(PY) -m sideline

sim:              ## open the voice simulator (served by the running server)
	@$(PY) -c "import webbrowser;webbrowser.open('http://127.0.0.1:8765/')" \
	  || echo "open http://127.0.0.1:8765/"

# The suite needs no network and no credentials. Secrets are blanked (an empty
# value beats .env) so a developer's own keys can never leak into a test run.
test:             ## full suite, offline
	@for t in $(sort $(wildcard tests/test_*.py)); do \
		echo "=== $$t"; \
		env SIDELINE_BEDROCK=off SIDELINE_STATE=memory SIDELINE_FOOTBALL_KEY= GROQ_API_KEY= \
		    AWS_ACCESS_KEY_ID= AWS_SECRET_ACCESS_KEY= AWS_PROFILE= AWS_BEARER_TOKEN_BEDROCK= \
		    $(PY) $$t || exit 1; \
	done
	@echo "\nall suites passed"

env:              ## show which environment variables are set (never prints a secret)
	$(PY) scripts/env_status.py

verify-data:      ## check the football feed key and quota (add ARGS=--tools to run every tool)
	$(PY) scripts/verify_data.py $(ARGS)

aws-check:        ## check the AWS integrations layer by layer
	$(PY) scripts/verify_aws.py

create-table:     ## create the DynamoDB table
	$(PY) scripts/create_table.py

stt-check:        ## speech-in accuracy on football phrases (needs a provider, and AWS for Polly)
	$(PY) scripts/verify_stt.py

compare-stt:      ## Nova Sonic against Groq Whisper, clean and noisy (needs both)
	$(PY) scripts/compare_stt.py

clean:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
