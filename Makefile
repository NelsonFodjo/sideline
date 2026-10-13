# python3 on most Linux and macOS; override with `make run PY=python`
PY ?= python3
export PYTHONPATH := .:tests

.PHONY: run sim test env verify-data next-matches route-check logs log-report aws-check create-table stt-check compare-stt clean

run:              ## start the server (needs SPORTMONKS_TOKEN; see README)
	$(PY) -m sideline

sim:              ## open the voice simulator (served by the running server)
	@$(PY) -c "import webbrowser;webbrowser.open('http://127.0.0.1:8765/')" \
	  || echo "open http://127.0.0.1:8765/"

# The suite needs no network and no credentials. Secrets are blanked (an empty
# value beats .env) so a developer's own keys can never leak into a test run.
test:             ## full suite, offline
	@for t in $(sort $(wildcard tests/test_*.py)); do \
		echo "=== $$t"; \
		env SIDELINE_LOG_DIR=off SIDELINE_BEDROCK=off SIDELINE_STATE=memory SPORTMONKS_TOKEN= \
		    AWS_ACCESS_KEY_ID= AWS_SECRET_ACCESS_KEY= \
		    $(PY) $$t || exit 1; \
	done
	@echo "\nall suites passed"

env:              ## show which environment variables are set (never prints a secret)
	$(PY) scripts/env_status.py

logs:             ## follow today's log file
	@tail -f logs/sideline-$$(date +%Y-%m-%d).log

log-report:       ## summarise the call logs: tools used, speed, declines, speech (ARGS=2026-10-17 for one day)
	$(PY) scripts/log_report.py $(ARGS)

next-matches:     ## the next matches in the leagues the token covers (to plan a demo; ARGS=21 for three weeks)
	$(PY) scripts/next_matches.py $(ARGS)

route-check:      ## does the voice agent pick the right tool? (real Nova, invented data, no feed calls)
	$(PY) scripts/route_check.py

verify-data:      ## check the football feed token and quota (add ARGS=--tools to run the core tools)
	$(PY) scripts/verify_data.py $(ARGS)

aws-check:        ## check the AWS integrations layer by layer
	$(PY) scripts/verify_aws.py

create-table:     ## create the DynamoDB table
	$(PY) scripts/create_table.py

stt-check:        ## speech-in accuracy on football phrases (needs a provider, and AWS for Polly)
	$(PY) scripts/verify_stt.py

compare-stt:      ## the AWS speech-in models head to head, clean and noisy (Voxtral, Nova Sonic)
	$(PY) scripts/compare_stt.py

clean:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
