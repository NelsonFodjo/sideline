# Architecture

## The inversion to understand first

**The client is the voice; we are the server.**

In the intended deployment the client is Alexa+: it does speech recognition,
chooses which tool a sentence maps to, writes the wording the listener
hears, speaks it and renders anything on screen, and we expose tools and
hold state. **That deployment is not reachable by hackathon participants**
(the add-on tooling is partner-only; see [OFFICIAL_RULES.md](OFFICIAL_RULES.md)).
So today the client is our own web page, `simulator/index.html`, which
speaks real MCP (initialize, tools/list, tools/call) to the server, as the
hackathon FAQ describes. Any MCP client works the same way.

One consequence holds either way: **the quality of a tool's description is
product surface.** The simulator agent and an MCP client choose a tool by
reading its description. A badly worded description is a bug the listener
experiences as "it keeps telling me the score when I asked what happened."

## The layers

```
   MCP client: the simulator (a web page), or any MCP client
                      |
         MCP / Streamable HTTP / 2025-11-25
                      |
             OUR MCP SERVER                       this repo
         |          |           |            |
     Bedrock    DynamoDB    poller        match data
     (language) (state)     (in-process)  (replay | live feed)
```

| Layer | Who owns it | Status |
|---|---|---|
| MCP client | the simulator agent bridges Nova tool use to the local MCP registry; external clients use `/mcp` | simulator: tested; Alexa+: unreachable |
| MCP server | this repo | tested, `tests/test_mcp_protocol.py` |
| Bedrock | AWS | Nova Micro invocation, MCP tool use and catch-up verified by `make aws-check` on 2026-10-13; live integration is not broadly tested |
| DynamoDB | AWS | written; **never run** (the in-memory store shares its logic and is tested) |
| Poller | this repo, a thread in the server | tested; an EventBridge variant is documented, not built |
| Match data | StatsBomb replay, or API-Football | replay: used; live: canned-response tests only |

## One question, end to end

The listener says **"what did I miss?"**

(In the simulator, the browser captures and transcribes speech, then sends
the text to `/agent/chat`. The server gives Nova the MCP tool schemas,
executes its selected tool through the registry, and returns Nova's final
wording. External MCP clients can still call the tools directly.)

1. The client captures the listener's speech.
2. It is transcribed and sent to Nova.
3. Nova selects `what_did_i_miss` from the MCP tool definitions; the server
   executes the registered tool and sends its result back to Nova.
4. Our server reads this listener's `last_told_at` from the store.
5. It pulls every logged event since, minus anything already told.
6. The tool returns structured event facts; in the simulator, Nova uses
   those facts to compose the catch-up (direct MCP mode can call Bedrock
   for a summary).
7. `last_told_at` moves forward; the event ids are recorded as told.
8. We return text plus structured detail.
9. Nova phrases the result, and the simulator speaks it.

The server side is one function; steps 1, 2 and 9 belong to the client.

## The two halves

**The request half** is ordinary: a tool is called, we answer.

**The background half** is the interesting one. `poller.py` runs whether
or not anyone is talking to Alexa. It is what makes "what did I miss"
answerable at all — a product that only fetches when asked cannot tell
you about a goal you were not in the room for, because by then you would
have to know to ask.

It is a thread inside the server process, and that is how the CloudFormation
stack runs it. An EventBridge Scheduler plus Lambda variant is documented
(`scripts/lambda_handler.py`) but not built or deployed. `poll_once()` is the
whole unit of work and does not know which is calling it.

Two decisions inside it worth knowing:

- **It polls an overlapping window** and leans on the store's dedupe,
  rather than tracking exactly where it got to. Feeds revise events: a
  goal gets an assist attached a minute later, a card is upgraded to red.
  Re-reading is cheap and correct; bookkeeping is neither.
- **It only polls fixtures somebody is following.** Polling every live
  match in the world is a good way to exhaust a request budget by
  lunchtime.

## No dependencies

The server imports nothing outside the Python standard library. That is
a deliberate choice, with three reasons:

1. **A judge can run it.** Clone, `python3 -m sideline`, hear a real
   answer. No virtualenv, no install step, no version conflict, no AWS
   account.
2. **Supply chain.** A public repo with a handful of transitive
   dependencies is a public repo with a handful of things that can be
   compromised between now and judging.
3. **It forced better decisions.** No web framework meant writing the
   Streamable HTTP transport properly rather than inheriting somebody's
   defaults — which is how the session handling, origin validation and
   notification semantics ended up actually matching the spec.

Two optional dependencies, each needed only when its feature is switched
on: **boto3** for the AWS paths, and **cryptography** for verifying RS256
tokens when `SIDELINE_AUTH=required` (HS256 tokens verify with the
standard library alone).

## Where state lives

`sideline/state/store.py`. Read it before anything else.

```
Listener                        Event
  listener_id                     id
  following      fixture id       fixture_id
  supports       team name        minute, stoppage
  last_told_at   match minute     kind  goal|card|substitution|var
  told_event_ids                  player, team, assist, detail
  language                        superseded_by
```

`gap_for()` and `mark_told()` live on the **base class**, not on each
backend. That is on purpose: the gap calculation is the heart of the
product, and it must not drift between the in-memory and DynamoDB
implementations.

### Why `told_event_ids` as well as `last_told_at`

They answer different questions. The timestamp answers *what window*.
The id set answers *did we already mention this specific thing*.

Both are needed. A listener can ask about one goal explicitly, then
later ask what they missed — and should not hear that goal twice.

### Why the marker never moves backwards

`mark_told()` refuses to lower it. A listener hearing the same goal twice
is worse than a listener hearing nothing: it makes them distrust
everything else the thing says.

## Precomputation

When the poller logs new events it also schedules background, grounded
summaries for each follower's current window (`sideline/summaries.py`), so
`what_did_i_miss` reads a cache instead of waiting on a model. See
[BEDROCK.md](BEDROCK.md) for what that does and does not guarantee.

## Failure behaviour

| Failure | What happens | Why |
|---|---|---|
| Provider down | `ProviderUnavailable`, tool returns a speakable line | A feed wobble must not reach the listener as a protocol error |
| Bedrock down or slow | Template path, silently | A correct answer quickly beats a nicer one late |
| Bedrock invents a score | Output discarded, template used | Guard in `bedrock._score_consistent` |
| No match followed | `ToolError` with "tell me which game" | "Which match?" is a reasonable thing to be asked |
| Unknown player | `ToolError` naming what was not found | Better than a confident wrong player |
| Unknown session | HTTP 404 | Tells the client to re-initialize rather than retry forever |

The distinction that matters: **protocol errors** are JSON-RPC errors;
**tool failures** are successful responses with `isError: true` and
something the listener can actually hear. Confusing the two is the most
common way an MCP server becomes unusable in a voice context.
