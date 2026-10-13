# Architecture

## The inversion to understand first

**The client is the voice; we are the server.**

In the intended deployment the client is Alexa+: it does speech recognition, chooses which tool a sentence maps
to, writes the wording the listener hears, speaks it and renders anything on screen, and we expose tools and
hold state. **That deployment is not reachable by hackathon participants** (the add-on tooling is partner-only;
see [HACKATHON.md](HACKATHON.md)). So today the client is a **simulated Alexa+**: our own web page, `simulator/index.html`, plus a voice
agent behind it, and both speak real MCP to the server, as the hackathon FAQ describes. Any MCP client works
the same way.

One consequence holds either way: **the quality of a tool's description is product surface.** The agent and any
MCP client choose a tool by reading its description. A badly worded description is a bug the listener
experiences as "it keeps telling me the score when I asked what happened."

## The layers

```
   MCP client: the simulated Alexa+ (a web page + a voice agent), or any MCP client
                              |
              MCP / Streamable HTTP / 2025-11-25
                              |
                     OUR MCP SERVER                          this repo
            |           |            |              |
        Bedrock     DynamoDB      poller       live football feed
        (wording,   (listener     (a thread    (Sportmonks)
         agent)      state)        in the
                                   server)
```

| Layer | Who owns it |
|---|---|
| MCP client | the simulator page opens a session and lists the tools; the voice agent makes every `tools/call` over `/mcp` ([`mcp/client.py`](../sideline/mcp/client.py)). External clients use `/mcp` directly |
| MCP server | this repo ([`mcp/server.py`](../sideline/mcp/server.py)) |
| Bedrock | AWS: Nova Micro writes the catch-up and, in the simulator, chooses tools; Nova 2 Sonic hears speech |
| Polly | AWS: speech out (generative voice), with word timings |
| DynamoDB | AWS: listener state and the event log (memory when no table is available) |
| Poller | this repo: a thread in the server process |
| Match data | the live feed, behind a provider interface ([`providers/`](../sideline/providers/)) |

What has actually been verified, on which dates, is in the README's table.

## One question, end to end

The listener says **"what did I miss?"**

1. The client captures the listener's speech. In the simulator the browser records it and the server
   transcribes it (Voxtral, or Nova Sonic as the fallback, both on Bedrock: see [SPEECH.md](SPEECH.md)).
2. `sideline/resolve.py` checks whether it answers a choice we just offered, and repairs misheard names.
3. Nova is given the tool definitions and selects `what_did_i_miss`.
4. The agent's MCP client calls `tools/call` on our own `/mcp`. The server validates the arguments and runs the tool.
5. The tool reads this listener's `last_told_at` from the store and pulls every logged event since, minus
   anything already told.
6. For the agent it returns the event facts (a header, `X-Sideline-Agent`, asks for facts rather than a
   paragraph, because the agent is a model and would only paraphrase one). For any other client, Bedrock
   composes the paragraph.
7. `last_told_at` moves forward; the event ids are recorded as told.
8. Nova phrases the result, Polly speaks it, and the page highlights each word as it is spoken.

The server side is steps 4 to 7; the rest belong to the client. A client such as Alexa+ would do steps 1, 3 and 8.

## The two halves

**The request half** is ordinary: a tool is called, we answer.

**The background half** is the interesting one. `poller.py` runs whether or not anyone is talking to the
client. It is what makes "what did I miss" answerable at all: a product that only fetches when asked cannot tell
you about a goal you were not in the room for, because by then you would have to know to ask. `poll_once()` is
the whole unit of work.

Two decisions inside it worth knowing:

- **It polls an overlapping window** and leans on the store's dedupe, rather than tracking exactly where it got
  to. Feeds revise events: a goal gets an assist attached a minute later, a card is upgraded to red. Re-reading
  is cheap and correct; bookkeeping is neither.
- **It only polls fixtures somebody is following.** Polling every live match in the world is a good way to
  exhaust a request budget by lunchtime. A match that is over is read once more and then left alone, and a match
  nobody follows any more is dropped from the list, so a finished game does not keep spending the hourly limit.

The protocol surface, what is implemented and what is not, is in [MCP.md](MCP.md).

## The simulator's own endpoints

`/voice/stt`, `/voice/tts`, `/voice/capabilities` and `/agent/chat` are the simulated Alexa+'s support and are not part of the MCP
surface. They spend AWS credits, so they are same-origin only, like `/mcp`: another web page cannot call them (403, and no
cross-origin headers are sent), and an upload over 12 MB of audio or 16 KB of text is refused unread with the connection
closed. The page is served by the server it talks to, so nothing has to be opened up. Pinned by `tests/test_simulator.py`.

## Which match you mean

Tools take what a person says, not an id. `sideline/finder.py` works out which match, played or to come, from a team, an
opponent, a day or a date: it gathers candidates, scores them, and either uses a clear winner or lists the options for the
listener to pick from. [FINDER.md](FINDER.md) has the algorithm and its limits.

## One product, many sports

Nothing above `sideline/sports/` names a sport. A `SportProfile` answers the handful of questions that vary
(what scores, what overturns a score, what is a headline, how time and scores are said, which moments a
listener can anchor the spoiler guard on) and every layer asks it rather than comparing against `"goal"`. A
fixture's `sport` key picks the profile; absent means football. See [SPORTS.md](SPORTS.md).

## Standard library first

The server imports nothing outside the Python standard library. That is a deliberate choice:

1. **A reviewer can run it.** Clone, set a token, `python3 -m sideline`. No virtualenv, no version conflict.
2. **Supply chain.** A public repo with a handful of transitive dependencies is a public repo with a handful of
   things that can be compromised between now and judging.
3. **It forced better decisions.** No web framework meant writing the Streamable HTTP transport properly rather
   than inheriting somebody's defaults, which is how session handling, origin validation and notification
   semantics ended up matching the spec.

Optional dependencies, each needed only when its feature is on: **boto3** (Bedrock, Polly, DynamoDB) and
**aws-sdk-bedrock-runtime** with **awscrt** (Nova Sonic speech in).

## Where state lives

`sideline/state/store.py`. Read it before anything else.

```
Listener                        Event
  listener_id                     id
  following      fixture id       fixture_id
  supports       team name        minute, stoppage
  last_told_at   match minute     kind          per sport: goal, card, basket, foul ...
  told_event_ids                  player, team, assist, detail, points
  language                        superseded_by
```

`gap_for()` and `mark_told()` live on the **base class**, not on each backend. That is on purpose: the gap
calculation is the heart of the product, and it must not drift between the in-memory and DynamoDB
implementations.

**Why `told_event_ids` as well as `last_told_at`.** They answer different questions. The timestamp answers
*what window*. The id set answers *did we already mention this specific thing*. A listener can ask about one goal
explicitly, then later ask what they missed, and should not hear that goal twice.

**Why the marker never moves backwards.** `mark_told()` refuses to lower it. A listener hearing the same goal
twice is worse than a listener hearing nothing: it makes them distrust everything else the thing says.

## Failure behaviour

| Failure | What happens | Why |
|---|---|---|
| The feed is down, refuses the key, or the quota is spent | `ProviderUnavailable`: the tool answers "The match data feed said: <the vendor's own error>. Try again shortly." and the voice agent says exactly that | A feed wobble must not reach the listener as a protocol error |
| Bedrock is on and fails, or invents a score | The failure is reported to the caller (a spoken decline); the listener's gap is **kept**, so asking again still works | Never a canned guess about a match the listener cannot see |
| Bedrock is off | The deterministic template, labelled `generated_by: template` | The fast tools never need a model |
| No match followed | `ToolError` with "tell me which game" | "Which match?" is a reasonable thing to be asked |
| Two matches fit | `ToolError` listing the options, remembered so a mispronounced answer can be resolved | Ambiguity is the listener's to settle |
| Unknown player | `ToolError` naming what was not found | Better than a confident wrong player |
| Unknown session | HTTP 404 | Tells the client to re-initialize rather than retry forever |

The distinction that matters: **protocol errors** are JSON-RPC errors; **tool failures** are successful responses
with `isError: true` and something the listener can actually hear. Confusing the two is the most common way an
MCP server becomes unusable in a voice context.
