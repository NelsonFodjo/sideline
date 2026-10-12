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

**Evidence** QuickStart, 2026-10-12. See FL-03. Sideline's own approach is
templates for fast tools and a configurable model timeout.

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
