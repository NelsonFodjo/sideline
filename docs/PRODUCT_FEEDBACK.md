# Product feedback

> Product feedback on every tool, API, or SDK you used: what you used it
> for, what worked well, what needs work, how onboarding felt, and
> whether you'd build with it again. Building with AWS services? Describe
> which ones and how, right here in your feedback answer.

Those five questions, answered per tool. Written as we went, not on the
last night.

---

## Alexa+ MCP Toolkit

**Used for** connecting a self-hosted MCP server to Alexa+ as an add-on.

**What worked well**

The client/server inversion is the right call and should be stated even
more loudly than it is. Not writing speech recognition, intent schemas,
slot types or response wording removed roughly everything that made
classic Alexa skill development slow. A tool with a good description is
genuinely all it takes.

Choosing MCP rather than a proprietary interface means the server we
wrote works unchanged against other MCP clients. We tested against a
generic client throughout and only connected the add-on near the end.
That is a real productivity win and worth marketing.

**What needs work**

1. **No way for a server to initiate.** The single biggest constraint on
   this product. Our use case — tell a blind listener a goal has gone in
   — is impossible, because the server cannot make the device speak. We
   redesigned around it and the result is arguably better, but the
   constraint should be documented prominently rather than discovered.
   We implement the SSE channel and hold it open in case this changes.

2. **Tool description guidance is thin.** Descriptions are the entire
   routing surface and we found no documented guidance on writing them
   for the router — length, whether to include example phrasings, how to
   disambiguate two adjacent tools. We worked it out by trial. A page on
   this would save every integrator the same week.

3. **No routing preview.** There is no way to ask "which tool would this
   sentence hit" without a round trip through a device. We built our own
   phrase-assertion test as a substitute. A CLI command taking an
   utterance and returning the chosen tool would be the highest-value
   developer tool you could ship.

4. **Regional availability.** The toolkit is documented as available in
   the United States. For a team outside it, the path to a working
   add-on is not obvious from the docs, and it is the first question a
   non-US developer has.

**Onboarding** Good once the mental model lands. The thing that took
longest was unlearning the assumption that we needed to handle
conversation.

**Would we build with it again** Yes.

---

## MCP specification 2025-11-25 / Streamable HTTP

**Used for** the transport, implemented from the spec with no SDK.

**What worked well** The spec is implementable directly. Session
semantics, the 202-for-notifications rule and the Origin guidance are all
unambiguous. We wrote a conforming server in standard library Python with
no reference implementation.

**What needs work**

1. **The 202 rule is easy to miss and expensive.** Returning a body for a
   notification makes clients hang. It is in the spec but deserves to be
   called out as a common failure.

2. **No official conformance suite.** We wrote `test_mcp_protocol.py`
   ourselves. A published suite would let every implementer prove
   correctness instead of hoping.

3. **`_meta` conventions are loose.** We used `_meta.ui` for MCP Apps and
   a namespaced `_meta.sideline` for timing. Clearer conventions would
   stop everyone inventing their own.

**Would we use it again** Yes.

---

## MCP Apps extension

**Used for** scoreboard, line-up and catch-up cards on screened devices.

**What worked well** Declaring a UI next to the tool, rather than in a
separate rendering layer, keeps related things together.

**What needs work** There is no declarative way to say *this card is
supplementary; the spoken text is authoritative*. For an accessibility
product that distinction is central, and we enforce it by convention and
code review. A manifest flag would make it checkable.

---

## Amazon Bedrock — Converse API, Claude 3.5 Haiku

**Used for** compressing a window of match events into one spoken
paragraph; a milestones mode for long absences; open questions that map
to no single tool; and switching register so the same facts can be
delivered the way people actually speak around a match.

**What worked well** Low-temperature, tightly grounded summarisation is
exactly what this needed. Instruction-following on "use only this data"
was strong enough that our scoreline guard rarely fires.

The Converse API was the right call over `invoke_model`: one request
shape across model families, so changing the model id is a config change
rather than a rewrite of the body. We started on Sonnet and moved to
Haiku for latency — a one-line change because of Converse.

Being able to pin a model id and get stable behaviour across a build week
mattered more than raw quality.

**What needs work**

1. **Cold start on first invoke.** The first call in a while is
   noticeably slower than subsequent ones. On a three-second budget that
   is the difference between the model path and the template path. A
   documented warm-up pattern, or a lighter first-call path, would help
   anyone doing latency-bound voice work.

2. **Timeout and retry defaults are wrong for voice.** The default retry
   behaviour will happily spend more time than a voice interaction has.
   We set `max_attempts=1` and a 3 s read timeout. A "low latency
   interactive" config preset would stop people discovering this in
   production.

3. **No native structured-output mode in the invoke path we used.** We
   want a paragraph and a list of grounded event ids. We get a paragraph
   and verify separately.

**Onboarding** Straightforward. Model access and region were the only
friction.

**Would we build with it again** Yes.

---

## AWS services

**DynamoDB** Single-table with a composite key handled both hot access
patterns in one query each — no GSI, no scan. On-demand capacity was the
right call for bursty match-day traffic. The conditional-put dedupe is
the one place a condition expression genuinely earned its keep: our
poller re-reads an overlapping window every cycle, and without it a
listener would be told about the same goal on every poll.

DynamoDB Local made this testable offline with no cloud spend and no IAM
round trip. Worth signposting more prominently for hackathon-scale
projects.

**EventBridge Scheduler** Correct tool for a 15-second poll. One thing we
hit: a schedule tight enough for live sport makes it easy to overrun a
third-party rate limit without noticing, because the failures are on the
third party's side. A worked example of "scheduler plus an external rate
limit" in the docs would be useful.

**Secrets Manager** Used for the football API key. Worked as expected.

**CloudWatch** We log per-tool latency. Getting from logs to a per-tool
p95 took longer than it should have for a metric this standard.

---

## Devpost submission process

**What worked well** The requirements are specific. "Your repo needs to
actually call the technology in code, not just mention it in a README" is
the clearest anti-vapour clause we have seen in a hackathon.

The friction log bonus is a good mechanism — it pays teams for the
feedback the sponsor actually wants.

**What needs work** The seven-day expiry on GitHub collaborator
invitations is documented but easy to trip over, because the natural
instinct is to add reviewers early. The warning deserves to be louder, or
the window longer.
