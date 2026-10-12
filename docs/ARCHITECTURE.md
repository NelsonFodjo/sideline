# Architecture

## The inversion to understand first

**Alexa+ is the client. We are the server.**

That catches people out, because voice development used to mean building
the voice part. It no longer does. Alexa+ does speech recognition, picks
which tool a sentence maps to, writes the sentence the listener hears,
speaks it, and renders anything on screen.

We expose tools and hold state. That is the whole job.

The practical consequence is that **the quality of our tool descriptions
is product surface**, not documentation. Alexa+ reads them to decide
routing. A badly worded description is a bug the listener experiences as
"it keeps telling me the score when I asked what happened."

## The layers

```
          Echo / Echo Show / Alexa app
                      |
              ALEXA+ SERVICE                      Amazon's
                      |
         MCP / Streamable HTTP / 2025-11-25
                      |
            ALEXA+ MCP ADD-ON                     we deploy
                      |
             OUR MCP SERVER                       this repo
         |          |           |            |
     Bedrock    DynamoDB   EventBridge   football feed
```

| Layer | Who owns it | What it does |
|---|---|---|
| Device | Amazon | Microphone, speaker, optional screen |
| Alexa+ service | Amazon | NLU, routing, wording, TTS, rendering |
| MCP add-on | Us, deployed with `alexa-ai` | Tool discovery, OAuth linking, protocol translation |
| MCP server | Us, this repo | Tools, event log, listener state |
| Bedrock | AWS | Language composition — only where it is needed |
| DynamoDB | AWS | State and the event log |
| EventBridge | AWS | Wakes the poller every 15 s |
| Football feed | Third party | The reach |

## One question, end to end

The listener says **"what did I miss?"**

1. Echo streams audio to Alexa+.
2. Alexa+ transcribes it and decides it belongs to our add-on.
3. The add-on calls `what_did_i_miss` over Streamable HTTP.
4. Our server reads this listener's `last_told_at` from the store.
5. It pulls every logged event since, minus anything already told.
6. Bedrock compresses them into one paragraph.
7. `last_told_at` moves forward; the event ids are recorded as told.
8. We return text plus structured detail.
9. Alexa+ phrases and speaks it.

We wrote one function. Steps 1, 2 and 9 are not ours and never will be.

## The two halves

**The request half** is ordinary: a tool is called, we answer.

**The background half** is the interesting one. `poller.py` runs whether
or not anyone is talking to Alexa. It is what makes "what did I miss"
answerable at all — a product that only fetches when asked cannot tell
you about a goal you were not in the room for, because by then you would
have to know to ask.

In production that is EventBridge Scheduler invoking a Lambda. Locally
it is a thread. `poll_once()` is the whole unit of work and does not know
which is calling it.

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

boto3 is the single optional dependency, needed only when the AWS paths
are switched on.

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

## Failure behaviour

| Failure | What happens | Why |
|---|---|---|
| Provider down | `ProviderUnavailable`, tool returns a speakable line | A feed wobble must not reach the listener as a protocol error |
| Bedrock down or slow | Template path, silently | A correct answer at 300 ms beats a nicer one at 5 s |
| Bedrock invents a score | Output discarded, template used | Guard in `bedrock._score_consistent` |
| No match followed | `ToolError` with "tell me which game" | "Which match?" is a reasonable thing to be asked |
| Unknown player | `ToolError` naming what was not found | Better than a confident wrong player |
| Unknown session | HTTP 404 | Tells the client to re-initialize rather than retry forever |

The distinction that matters: **protocol errors** are JSON-RPC errors;
**tool failures** are successful responses with `isError: true` and
something the listener can actually hear. Confusing the two is the most
common way an MCP server becomes unusable in a voice context.
