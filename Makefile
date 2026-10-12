# python3 on most Linux and macOS; override with `make run PY=python`
PY ?= python3
export PYTHONPATH := .:tests

.PHONY: run test smoke sim clean lint

run:              ## start the MCP server against the recorded match
	$(PY) -m sideline

run-fast:         ## same, but the match runs 20x so you can see events land
	SIDELINE_REPLAY_SPEED=20 $(PY) -m sideline

test:             ## full suite, no network, no credentials
	@for t in tests/test_clean_clone.py tests/test_routing_phrases.py tests/test_language.py \
	          tests/test_tools.py tests/test_what_did_i_miss.py \
	          tests/test_broadcast_sync.py tests/test_pronouns.py \
	          tests/test_mcp_protocol.py; do \
		echo "=== $$t"; $(PY) $$t || exit 1; \
	done
	@echo "\nall suites passed"

smoke:            ## exercise every tool against a running server
	$(PY) scripts/smoke_test.py

verify-aws:       ## check the AWS setup layer by layer
	$(PY) scripts/verify_aws.py

sim:              ## open the voice simulator (server must be running)
	@python3 -c "import webbrowser,os;webbrowser.open('file://'+os.path.abspath('simulator/index.html'))" \
	  || echo "open simulator/index.html"

clean:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
