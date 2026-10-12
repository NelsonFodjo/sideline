# Start here

## Run it, in thirty seconds

```bash
python3 -m sideline
```

No install, no virtualenv, no `PYTHONPATH`, no AWS account, no API key.
It runs against a real match, replayed. In a second terminal:

```bash
python3 scripts/smoke_test.py      # every tool, printing what a listener hears
make test                          # eight suites, no network, no credentials
```

Then open `simulator/index.html` and talk to it.

## If you are judging

| Question | Where |
|---|---|
| Does it meet the requirements? | [COMPLIANCE.md](COMPLIANCE.md) — every rule, mapped |
| What does it actually do? | [../README.md](../README.md) |
| Is the MCP real? | `sideline/mcp/server.py`, proved by `tests/test_mcp_protocol.py` |
| Where is Bedrock? | [BEDROCK.md](BEDROCK.md) — and where it is deliberately *not* |
| Where are the AWS integrations? | [MINI_CHALLENGES.md](MINI_CHALLENGES.md) |
| Product feedback | [PRODUCT_FEEDBACK.md](PRODUCT_FEEDBACK.md) — the five questions, per tool |
| Friction log | [FRICTION_LOG.md](FRICTION_LOG.md) — nine entries, six columns |
| Feature requests | [FEATURE_REQUESTS.md](FEATURE_REQUESTS.md) |
| Honest self-assessment | [WHERE_WE_WIN.md](WHERE_WE_WIN.md) |

## If you are building on it

Read these two files before anything else:

**`sideline/state/store.py`** — the product is one field. `last_told_at`
is when we last told *this* listener anything about *this* match. It is
how "what did I miss" works without the listener saying how long they
were away, and Alexa+ has no equivalent.

**`sideline/mcp/registry.py`** — tool descriptions are product surface,
not documentation. Alexa+ reads them to route. Three rules at the top of
that file, and `tests/test_routing_phrases.py` holds them.

Then: [ARCHITECTURE.md](ARCHITECTURE.md), [TOOLS.md](TOOLS.md),
[CONTRIBUTING.md](../CONTRIBUTING.md).

## If you are setting up AWS

[AWS_SETUP.md](AWS_SETUP.md), seven steps with a check after each.

The one that catches everyone is step 3: **Bedrock model access is off
by default**, and the error it produces reads like a credentials problem
when it is not.

```bash
python3 scripts/verify_aws.py     # names the layer that failed
```

## Two mistakes worth knowing about

Both are written up rather than quietly fixed, because the pattern
matters more than either instance.

**The clock.** The first spoiler guard asked the listener to read the
minute on their screen. They cannot see the screen — that is the premise
of the product. It now anchors on what they *hear*: kick-off, half time,
a goal going in.

**The simulator.** It shipped with push-to-talk, suggestion chips and a
text box. All three need sight. It is now hands-free.

Twice is a pattern, so it is a rule in [ACCESSIBILITY.md](ACCESSIBILITY.md):
before adding any input, ask what it requires of the listener. If the
answer involves looking at something, it is the wrong input.
