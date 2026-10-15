# python3 on most Linux and macOS; PY selects the interpreter when .venv is created
PY ?= python3
export PYTHONPATH := .:tests

.PHONY: run sim test bench env verify-data next-matches route-check logs log-report aws-check create-table stt-check compare-stt clean

run:              ## start the server (bootstraps dependencies; live ESPN multi-sport)
	PY="$(PY)" ./run.sh

# The URL and the log folder come from the same settings the server reads (environment, then .env).
SIM_URL = $(PY) -c "from sideline.config import CONFIG as C; h = C.host if C.host not in ('', '0.0.0.0', '::') else '127.0.0.1'; print('http://%s:%d/' % ('[%s]' % h if ':' in h else h, C.port))"

sim:              ## open the voice simulator (served by the running server)
	@url="$$($(SIM_URL))" && { $(PY) -c "import sys, webbrowser; webbrowser.open(sys.argv[1])" "$$url" \
	  || echo "open $$url"; }

# The suite needs no network and no credentials. Secrets are blanked (an empty
# value beats .env) so a developer's own keys can never leak into a test run.
test:             ## full suite, offline
	@for t in $(sort $(wildcard tests/test_*.py)); do \
		echo "=== $$t"; \
		env SIDELINE_LOG_DIR=off SIDELINE_BEDROCK=off SIDELINE_STATE=memory \
		    AWS_ACCESS_KEY_ID= AWS_SECRET_ACCESS_KEY= \
		    $(PY) $$t || exit 1; \
	done
	@echo "\nall suites passed"

bench:            ## tool cost and tools/list size, offline (BENCH_ARGS="--check" to enforce the budgets)
	$(PY) scripts/bench.py $(BENCH_ARGS)

env:              ## show which environment variables are set (never prints a secret)
	$(PY) scripts/env_status.py

logs:             ## follow today's log file
	@dir="$$($(PY) -c "from sideline.config import CONFIG; d = CONFIG.log_dir.strip(); print('' if d.lower() in ('', 'off', 'none', '0', 'false', 'no') else d)")" && \
	  if [ -z "$$dir" ]; then echo "logs are off (SIDELINE_LOG_DIR)"; \
	  else tail -f "$$dir/sideline-$$(date +%Y-%m-%d).log"; fi

log-report:       ## summarise the call logs: tools used, speed, declines, speech (ARGS=2026-10-17 for one day)
	$(PY) scripts/log_report.py $(ARGS)

next-matches:     ## the next matches across all covered sports (to plan a demo; ARGS=21 for three weeks)
	$(PY) scripts/next_matches.py $(ARGS)

route-check:      ## does the voice agent pick the right tool? (real Nova, invented data, no feed calls)
	$(PY) scripts/route_check.py

verify-data:      ## check the live ESPN feed (add ARGS=--tools to run the core tools)
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
