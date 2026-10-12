# Start here

## Run it, in thirty seconds

```bash
python3 -m sideline
```

No install, no virtualenv, no `PYTHONPATH`, no AWS account, no API key.
It runs against a real match, replayed. In a second terminal:

```bash
python3 scripts/smoke_test.py      # every tool, printing what a listener hears
make test                          # sixteen suites, no network, no credentials
```

Then open http://127.0.0.1:8765/ (served by the running server; `make sim`) and talk to it.

## If you are judging

| Question | Where |
|---|---|
| Does it meet the requirements? | [COMPLIANCE.md](COMPLIANCE.md) — every rule, mapped |
| What does it actually do? | [../README.md](../README.md) |
| Is the MCP real? | `sideline/mcp/server.py`, proved by `tests/test_mcp_protocol.py` |
| Where is Bedrock? | [BEDROCK.md](BEDROCK.md) — and where it is deliberately *not* |
| Where are the AWS integrations? | [MINI_CHALLENGES.md](MINI_CHALLENGES.md) |
| Product feedback | [PRODUCT_FEEDBACK.md](PRODUCT_FEEDBACK.md) — the five questions, per tool |
| Friction log | [FRICTION_LOG.md](FRICTION_LOG.md) — eight entries, each with a cited source |
| Feature requests | [FEATURE_REQUESTS.md](FEATURE_REQUESTS.md) |
| What is measured, and what is not | [EVIDENCE.md](EVIDENCE.md) |
| The official rules, with sources | [OFFICIAL_RULES.md](OFFICIAL_RULES.md) |
| Self-assessment (opinion) | [WHERE_WE_WIN.md](WHERE_WE_WIN.md) |

## If you are building on it

Read these two files before anything else:

**`sideline/state/store.py`** — the product is one field. `last_told_at`
is when we last told *this* listener anything about *this* match. It is
how "what did I miss" works without the listener saying how long they
were away.

**`sideline/mcp/registry.py`** — tool descriptions are product surface,
not documentation: a client reads them to choose a tool. Three rules at the
top of that file, and `tests/test_routing_phrases.py` holds them.

Then: [ARCHITECTURE.md](ARCHITECTURE.md), [TOOLS.md](TOOLS.md),
[CONTRIBUTING.md](../CONTRIBUTING.md).

## If you are setting up AWS

[AWS_SETUP.md](AWS_SETUP.md), seven steps with a check after each. Nova
Bedrock has been checked once against a real account; DynamoDB and the
deployment have not (see [EVIDENCE.md](EVIDENCE.md)).

Bedrock model access has to be granted per account and model; an access
failure can look like a credentials error.

```bash
python3 scripts/verify_aws.py     # names the layer that failed
```

## A rule worth knowing

Before adding any input, ask what it requires of the listener. If the
answer involves looking at something, it is the wrong input. It is why the
spoiler guard anchors on what the listener *hears* and the simulator is
hands-free. See [ACCESSIBILITY.md](ACCESSIBILITY.md).
