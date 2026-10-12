# Product feedback

The hackathon requires, for **each tool, API or SDK used**: what you used
it for, what worked well, what needs work, how onboarding felt (zero to
hello world), and whether you would build with it again, and why.

**How to read this page.** Every statement here is either
(a) something a test or a measurement in [EVIDENCE.md](EVIDENCE.md)
backs, (b) something read in the cited documentation on the stated date,
or (c) marked **`TODO(you)`**, which only a hands-on run can answer.
Nothing here claims experience that has not happened. **Do not submit
while any `TODO(you)` remains**: answer it from a real run, or delete the
section if you did not use the thing. "Would you build with it again?" is
yours to answer honestly in each section.

AWS services used must also be described in this answer on the Devpost
form (rules, AWS Builder mini challenge).

---

## 1. Alexa+ MCP add-on documentation (read; the toolkit itself was not usable)

**Used for** Designing the server to the Alexa+ requirements: the
[QuickStart](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html),
[Account Linking](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-account-linking.html)
and the Design Guide pages on
[tools and schema](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-addon-tools-schema-data-design.html)
and the [conversation surface](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-addon-conversation-surface.html),
read 2026-10-12. **The CLI, MCP Toolkit and Web Simulator were never used**:
the hackathon FAQ says they are partner-only.

**What worked well**
- The Design Guide's tool rules are concrete and usable: one customer
  intent per tool, a description that says when to call it, no overlapping
  tools, declare only parameters you honour, always return something.
- The QuickStart states the protocol version (2025-11-25), the transport
  (Streamable HTTP) and a response-time target (500 ms) plainly.

**What needs work** (each is a friction-log entry with its evidence)
- Access: the setup pages show CLI commands without saying the tooling is
  partner-only (FL-01).
- The 401 rule contradicts the MCP authorization spec and says so only by
  omission (FL-02).
- A 500 ms target with no pattern for tools whose responses a model composes (FL-03).
- Whether a server can speak first is not stated on the conversation-surface page (FL-04).

**Onboarding** Reading the docs to a clear picture of the requirements was
quick. Discovering that none of the tooling is reachable took the FAQ.

**Would you build with it again?** `TODO(you)`: yes or no, and why.

## 2. Model Context Protocol, spec 2025-11-25, Streamable HTTP

**Used for** The server itself ([sideline/mcp/server.py](../sideline/mcp/server.py)),
written with the standard library, no SDK.

**Evidence** `tests/test_mcp_protocol.py` passes nine checks: initialize
and session id, notification gets 202 with no body, `tools/list`, a tool
call, invalid-params rejection, method-not-found, unknown session gets 404,
batch requests, and DELETE ends the session. EVIDENCE.md records the
negotiated version and the nine tools. These are *our own* conformance
tests, written from our reading of the spec; no official suite was run
(none was found).

**What worked well** `TODO(you)`: what in the spec was clear.
**What needs work** `TODO(you)`: what you had to guess.
**Onboarding** `TODO(you)`.
**Would you build with it again?** `TODO(you)`.

## 3. Amazon Bedrock, Converse API, Claude 3.5 Haiku

**Used for** Composing the catch-up paragraph, long-absence milestones and
translation ([sideline/language/bedrock.py](../sideline/language/bedrock.py)).
Guarded: a generated scoreline that disagrees with the real one is
discarded (tested in `tests/test_language.py`).

**Status: not yet called against a live account.** No Bedrock request has
been made, so there is no latency, quality or availability observation to
report.

**What worked well** `TODO(you)`: after `make aws-check`.
**What needs work** `TODO(you)`: cold-start latency, model access flow,
error clarity. Record the real `latencyMs` figures the server logs.
**Onboarding** `TODO(you)`: account to first successful call.
**Would you build with it again?** `TODO(you)`.

## 4. Amazon DynamoDB

**Used for** Listener state and the match event log, single table
([sideline/state/dynamo.py](../sideline/state/dynamo.py), table definition in
`scripts/create_table.py` and `deploy/sideline.yaml`).

**Status: written, not run.** The store logic is exercised through the
in-memory implementation that shares its base class (`gap_for`,
`mark_told`); DynamoDB itself, and DynamoDB Local, have not been run.

`TODO(you)`: all five answers, after `make create-table` and a real run.

## 5. Amazon Polly and Amazon Transcribe (simulator voice)

**Used for** Speech out with word-level speech marks, and streaming speech
in ([sideline/voice.py](../sideline/voice.py)).

**Status: written, not run** against a live account.

`TODO(you)`: all five answers, after trying the simulator with credentials.

## 6. AWS Secrets Manager, CloudWatch (Embedded Metric Format), App Runner, ECR, CloudFormation

**Used for** Football-key retrieval; per-tool latency metrics; hosting;
the stack that creates them.

**Status.** Secrets retrieval is unit-tested with a fake client. The metric
line format is unit-tested (`tests/test_aws_helpers.py`) but never viewed in
CloudWatch. `deploy/sideline.yaml` passes `cfn-lint` and has **never been
deployed**. Per the FAQ, hosting is not required for judging, so deploying
is optional.

`TODO(you)`: answer only for the services you actually use; delete the rest.

## 7. StatsBomb Open Data (third-party data) — hands-on findings

**Used for** The bundled real match, Tottenham 2-2 Arsenal, 5 March 2016,
built with `scripts/build_statsbomb_replay.py`.

**What worked well** The data is public, structured and complete enough to
replay a match with goals, cards, substitutions, a VAR event and line-ups.

**What needs work** Three things were found by replaying a real match and
are pinned by `tests/test_statsbomb.py`:
1. A second yellow card is a distinct card name ("Second Yellow"), not a
   red, so a naive mapping reports a sending-off as a booking.
2. Some bookings are filed under "Bad Behaviour" rather than "Foul
   Committed", so a mapping that only reads fouls drops them.
3. Line-up files are in no positional order, so reading them as listed
   puts a forward in goal. Position ids (1 = goalkeeper) fix the order.
Also, the events file does not carry the referee; it is in the matches file.

**Onboarding** The repository layout (competitions, matches, events,
lineups) is simple to navigate.

**Terms** Attribution to StatsBomb **and use of their logo** is requested
when publishing. We attribute in text and do not include the logo (the
video rules forbid third-party trademarks without permission).

**Would you use it again?** `TODO(you)`.

## 8. API-Football (live data) — not used yet

The provider is written against its documented response shape
(`sideline/providers/apifootball.py`) and tested with canned responses
(`tests/test_apifootball.py`). Its vendor site blocked automated reading, so
its free-tier limits and update frequency are **unverified**. Answer the
five questions only after `make verify-data` with a real key; otherwise
delete this section.

## 9. Devpost and the hackathon materials

**What worked well** The rules page is specific about submission
requirements, judging stages and criteria, and the FAQ answers the
partner-only question directly.

**What needs work** The FAQ still explains how to request AWS credits while
the rules page says the codes ran out on 7 October (FL-05).

**Would you do it again?** `TODO(you)`.
