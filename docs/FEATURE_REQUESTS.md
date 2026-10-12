# Feature requests

> Optional: what you'd want built, why it matters, and how urgent it is
> (critical / important / nice-to-have).

Written from building this, not from a wish list. Each one is something
we hit.

---

### FR-01 — Server-initiated speech, with user opt-in

**Urgency: critical**

**What** A way for an MCP add-on to push a short message to the device,
which the listener has explicitly opted into per add-on.

**Why it matters** This is the single biggest constraint we met. Our
original design told a blind listener a goal had gone in. It is
impossible: the server cannot make the device speak, so the listener
must already know something happened in order to ask about it — which is
exactly what they cannot do.

We redesigned around it and the result is arguably better. But the
category this blocks is large and it is not ours alone: accessibility
alerts, safety notifications, anything time-critical. Every one of them
runs into the same wall.

Opt-in matters. Nobody wants an add-on that can interrupt them by
default. But "the user asked for this specific thing and can turn it
off" is a different proposition from unsolicited speech.

---

### FR-02 — Utterance-to-tool routing preview in the CLI

**Urgency: important**

**What** `alexa-ai test-utterance "what did I miss"` → the tool it would
route to, and why.

**Why it matters** Tool descriptions are the entire integration surface
for an MCP add-on, and there is currently no way to see what the router
does with one short of a round trip through a device. Each iteration is
minutes rather than seconds.

For a platform whose whole developer story is "write good tool
descriptions", not being able to test them is the gap felt soonest. We
built a phrase-assertion test as a substitute, but it tests our text,
not the router.

This would be the highest-value developer tool you could ship.

---

### FR-03 — Guidance on writing tool descriptions for the router

**Urgency: important**

**What** A documented page of patterns: length, whether to include
example phrasings, how to disambiguate two adjacent tools, and whether
to write for a human or for the model.

**Why it matters** We worked out three rules by trial — lead with
intent, embed the phrasings listeners actually use, and explicitly name
the adjacent tool you are *not*. That last one is non-obvious and bites
anybody with more than three tools, because two close descriptions turn
routing into a coin toss.

A page on this would save every integrator the same week.

---

### FR-04 — A declarative "this UI is supplementary" flag in MCP Apps

**Urgency: important**

**What** A manifest field asserting that a tool's spoken text is
authoritative and its UI payload is an enhancement.

**Why it matters** For an accessibility product this distinction is the
whole design. We enforce it by convention and code review: nothing
essential may live only in the card, because a listener on a voice-only
Echo would never hear it.

A flag would make that checkable rather than cultural — and it would let
the platform surface which add-ons are safe on voice-only devices.

---

### FR-05 — A low-latency interactive config preset for Bedrock

**Urgency: nice-to-have**

**What** A documented boto3 config for voice and real-time use, and a
note on first-invoke latency after idle.

**Why it matters** The default retry behaviour will happily spend more
wall-clock time than a voice interaction has. A retried call is a wasted
call — by the time it lands, the template answer would have been better.
We set `max_attempts=1` with a 3 s read timeout and found this by
measuring, not by reading.

The cold-start behaviour matters for match-day products specifically:
the first call is the one a listener notices.

---

### FR-06 — Nova Sonic that keeps word timings

**Urgency: nice-to-have**

**What** Word-level timing marks on Nova Sonic's audio output, the way
Polly returns speech marks.

**Why it matters** Nova Sonic is the obvious model for this product — a
unified speech-to-speech path with interruption handling is exactly the
interaction we built by hand. We did not use it, for one reason: it
streams audio chunks, and we need to know which word is being spoken at
each millisecond. That is what drives the reading animation, and it is
the thing sighted people in the room respond to.

Polly gives us those marks; Nova Sonic does not. So we have the better
model on one side and the better instrumentation on the other, and the
instrumentation won.

A timing event alongside the audio stream would let accessibility
products use the stronger model without giving up captioning,
highlighting, or anything else that needs to know where the voice is.

(Also worth noting: the experimental SDK and the Python 3.12+ floor make
it a hard thing to stake a hackathon demo on. That will age out; the
timing gap will not.)

---

### FR-07 — Published MCP conformance suite

**Urgency: nice-to-have**

**What** An official test suite an implementer can run against their
server.

**Why it matters** We implemented the transport from the spec with no
SDK and wrote our own conformance tests. They pass, but we are grading
our own work. A published suite would let every implementer prove
correctness instead of hoping — and would catch the easy misses, like
returning a body for a notification, which makes clients hang.
