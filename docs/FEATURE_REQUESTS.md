# Feature requests

> Optional in the submission: what you would want built, why it matters,
> and how urgent it is (critical / important / nice-to-have).

Each request cites what it rests on. None claims a hands-on experience that
has not happened.

---

### FR-01 — State whether an MCP add-on may speak first, and let users opt in

**Urgency: critical**

**What** Either an explicit statement that servers cannot initiate speech,
or a way to push a short message that the listener has opted into per add-on.

**Why it matters** A live-sport companion for blind listeners wants to say
"goal" when it happens. Without server-initiated speech the listener must
already suspect something happened in order to ask. Accessibility alerts
and safety notifications face the same limit.

**Evidence** The conversation-surface page describes a turn-based model and
does not address this (read 2026-10-12). The product is designed around
on-demand questions; the server holds an SSE channel open and sends nothing,
ready for it.

### FR-02 — Put the access note where the commands are

**Urgency: important**

**What** "Preview, select partners only" at the top of every page that
shows `alexa-ai` commands.

**Evidence** FAQ, 2026-10-12: the note is "sometimes missing from individual
setup-guide pages, which has caused some confusion". See FL-01.

### FR-03 — Document the 401 deviation and when it ends

**Urgency: important**

**What** Say that Alexa+ requires a 401 without `WWW-Authenticate`, why, and
when the standard header will be supported.

**Evidence** QuickStart, 2026-10-12. See FL-02.

### FR-04 — A pattern for tools whose answers a model composes

**Urgency: important**

**What** Guidance for a 500 ms target when a tool calls a language model:
precomputed summaries, streaming, or a declared longer budget.

**Evidence** QuickStart, 2026-10-12. See FL-03. Sideline's approach is
templates for the fast tools and an honest two-second catch-up; a precompute cache
was built, never measured against a real model, and removed.

### FR-05 — A "this UI is supplementary" signal for MCP Apps

**Urgency: nice-to-have**

**What** A declaration that a tool's spoken text is authoritative and its UI
payload is an enhancement.

**Why it matters** For an accessibility product, nothing essential may live
only in a card. Today that is enforced by convention in this repo; a
declared flag would make it checkable and let a platform tell which add-ons
are safe on voice-only devices. This is a design opinion, not an
observation about the current platform.

### FR-06 — A published MCP conformance suite

**Urgency: nice-to-have**

**What** An official test suite an implementer can run against a server.

**Why it matters** This server's transport was written from the spec with no
SDK and checked by our own nine tests (`tests/test_mcp_protocol.py`). That
is grading our own work. No official suite was found in the reading done for
this project.

### FR-07 — Guidance on how many MCP tools a voice assistant can choose among

**Urgency: important**

**What** A published limit, or a recommended pattern, for the size of a tool list a host model is expected to handle:
how many tools, how long their descriptions may be, and whether a host narrows the list before the model sees it.

**Why it matters** This server offers 30 tools, about 8,000 tokens of descriptions on every turn
(`scripts/bench.py`, `docs/bench-baseline.json`). With the whole list offered, the models we tried on Bedrock sent a
clear request to the wrong tool, or to none, on a measurable share of 79 test phrasings (FL-25). We do not know what
Alexa+ does with a server's tool list, so we cannot tell whether to ship fewer, larger tools or many small ones. That is
the first design choice every MCP author makes, and nothing we read answers it.

### FR-08 — State the retry behaviour and error types of Bedrock Converse calls

**Urgency: nice-to-have**

**What** In the Converse documentation, say what the SDK's retry setting counts, and which error codes are worth one
quick retry (throttling, service unavailable, model not ready) and which are not.

**Why it matters** `max_attempts=1` still made two attempts (FL-21), so a connect timeout cost double what we had
budgeted. During routing evaluations on an on-demand account, runs of 79 calls were throttled often enough to change the
score until the harness waited and retried. Both are discoverable only by measuring.

### FR-09 — Make truncation visible in ESPN's public scoreboard

**Urgency: nice-to-have** (a third-party API, not an AWS one)

**What** Return a total and a "more available" flag with the scoreboard response, and document `limit`.

**Why it matters** The scoreboard silently stops at 100 events unless `limit=500` is passed (FL-23). A client that does
not know sees a day with matches missing and no sign that anything was cut off. For a product that must not say a match
does not exist, silence is the worst failure.
