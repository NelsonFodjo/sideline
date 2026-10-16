# Architecture

## The inversion to understand first

**The client is the voice; we are the server.**

In the intended deployment the client is Alexa+: it does speech recognition, chooses which tool a sentence maps
to, writes the wording the listener hears, speaks it and renders anything on screen, and we expose tools and
hold state. **That deployment is not reachable by hackathon participants** (the add-on tooling is partner-only;
see [HACKATHON.md](HACKATHON.md)). So today the client is a **simulated Alexa+**: our own web page, `simulator/index.html`,
and a thin host on Bedrock, Amazon Nova Pro by default (`SIDELINE_BEDROCK_MODEL` can name another). For each question it
gives the model a shortlist from the live MCP catalog (four core tools plus up to four picked by keyword, each with its full
description and schema), then dispatches only calls for tools in that catalog. A few plain questions ("what's the score?")
skip the model: a fixed pattern runs one tool. Any MCP client can connect to the same server.

One consequence holds either way: **the quality of a tool's description is product surface.** The agent and any
MCP client choose a tool by reading its description. A badly worded description is a bug the listener
experiences as "it keeps telling me the score when I asked what happened."

## The layers

```
   MCP client: the simulated Alexa+ (a web page + Nova Pro/Bedrock host), or any MCP client
                              |
              MCP / Streamable HTTP / 2025-11-25
                              |
                     OUR MCP SERVER                          this repo
            |           |            |              |
        Bedrock     DynamoDB      poller       live sports feed
   (Nova Pro:         (listener   (a thread    (ESPN Multi-Sport CDN)
    wording, tool     state)       in the
    host)                          server)
```

| Layer | Who owns it |
|---|---|
| MCP client | the host fetches `initialize` instructions and `tools/list`, gives a shortlist of the live tool definitions to the model, then makes every selected `tools/call` over `/mcp` ([`simulator/mcp_client.py`](../simulator/mcp_client.py)). External clients use `/mcp` directly |
| MCP server | this repo ([`mcp/server.py`](../sideline/mcp/server.py)) |
| Bedrock | AWS: Amazon Nova Pro writes the catch-up and chooses among the shortlisted MCP tools; Mistral Voxtral Small hears speech first, Nova 2 Sonic as the fallback |
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
3. The host discovers `tools/list` over MCP and gives the model (Nova Pro by default) a shortlist, with full descriptions
   and schemas. For a few plain questions a fixed pattern picks the tool and no model is called.
4. The model calls the fitting tool or asks a focused clarification. If it answers a fact question with no tool, it is
   asked again and must call one.
5. The host's MCP client calls `tools/call` on `/mcp`. The server validates the arguments and runs the tool.
6. The tool reads this listener's `last_told_at` from the store and pulls every logged event since, minus
   anything already told.
7. For the simulator's agent it returns the event facts (a header asks for facts rather than a
   paragraph, because the agent's model would only paraphrase one; `generated_by: tool-data`). For any other
   client, Bedrock composes the paragraph.
8. `last_told_at` moves forward; the event ids are recorded as told.
9. The model phrases the result, Polly speaks it, and the page highlights each word as it is spoken.

The server side is steps 5 to 8; the rest belong to the client. In the simulator step 2 runs in the host
(`simulator/host.py`, using `sideline/resolve.py`); a client such as Alexa+ would do steps 1, 3, 4 and 9 itself.

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
  nobody follows any more is dropped from the list, so a finished game does not keep costing requests. (ESPN publishes
  no rate limit for these endpoints; this is to be a light user of them, not to stay under a known cap.)

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

The server can start without third-party packages; AWS integrations are optional
when using `python3 -m sideline` directly. The `./run.sh` launcher creates an
isolated `.venv` and installs `requirements.txt` so those integrations are
available without changing the system Python. That separation is deliberate:

1. **A reviewer can run it.** Clone, then `./run.sh`. No token is needed locally (`SIDELINE_AUTH_TOKEN` is optional, for
   a server exposed beyond the machine). Its dependencies stay in the project `.venv`.
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
  sport          active sport
  broadcast_offset
```

`gap_for()` and `mark_told()` live on the **base class**, not on each backend. That is on purpose: the gap
calculation is the heart of the product, and it must not drift between the in-memory and DynamoDB
implementations.

**Two tiers of memory, on purpose.** What the MCP server keeps about a listener is durable (DynamoDB): the match they follow,
their team, their settings, their broadcast delay, and what they have heard. The conversation itself, and the topic being
discussed (*"and them?"*, *"what about the second one?"*), is **session memory**: held in the host's process, forgotten after
thirty idle minutes or a restart, and never written to the table. That keeps verbatim questions out of storage, saves a read
and a write of the whole profile on every turn, and stops a restarted server from repeating an answer from yesterday instead of
asking for what is new. A listener can end the session's memory by saying "forget that" or "start over" (the followed match
and settings stay), and erase what the server keeps with "forget everything about me" (`set_preferences` with
`forget: "everything"`, a tool any MCP client can call).

**Why `told_event_ids` as well as `last_told_at`.** They answer different questions. The timestamp answers
*what window*. The id set answers *did we already mention this specific thing*. A listener can ask about one goal
explicitly, then later ask what they missed, and should not hear that goal twice.

**Why the marker never moves backwards.** `mark_told()` refuses to lower it. A listener hearing the same goal
twice is worse than a listener hearing nothing: it makes them distrust everything else the thing says.

## Where the time goes

Measured against the live ESPN feed on 2026-10-15 (`scripts/convo.py`, three conversation batches; `make bench` for the
offline cost of each tool). These are what we saw, not targets:

- **One tool call, answers cached:** a few milliseconds of our own work; the feed's requests are the cost.
- **A question that needs the feed, cold:** about 0.4 to 1.5 s for one lookup, about 3 s for the first question about a
  match (a team search, two schedules and the match summary: 3 requests), and 4 to 5 s for a name the search cannot find.
  Before the changes in this repository's history the same first question took 116 requests and 18 s.
- **A question the fast path answers** (score, table, fixtures): no model call, so the tool's time is all of it.
- **A question that goes through a model:** one or two Bedrock calls, about 1 to 3 s each depending on the model.
- **With DynamoDB as the state, from a distant region:** each call to the table took about 340 ms from Mauritius to
  us-east-1, and a cold first follow made 26 of them one after another (about 9 of its 11 seconds). Now it makes 10, the
  independent ones at the same time, the server's own records are kept while this process is the only writer, and a new
  follow reads only the match it just followed: 4.5 s for the tool alone (6.3 s with the model, measured on 2026-10-15),
  and 0 to 3 s for the questions after it. Live match data is never kept: it is read from the feed on every question
  (5 seconds at most, so the tools one question calls share one read). Opening the connections at start-up (`warm`)
  takes the first question's share of that off the first listener.
- **Speech:** Polly and the speech-in models add their own time on top; the page's Dev log (bottom-left, or Alt+D)
  shows each part for every question.

What keeps repeat questions cheap is the cache in `sideline/cache.py`: bounded, lifetimes by kind of data (a match that
is over is kept for hours, a live scoreboard or a match in play for 5 seconds), and one request shared by everyone asking for the same page
at once. See [ESPN_NOTES.md](ESPN_NOTES.md) for the endpoint facts behind it.

## Failure behaviour

| Failure | What happens | Why |
|---|---|---|
| The feed cannot be reached | `ProviderUnavailable`: the tool answers "Sorry, an error occurred. Please try rephrasing your question for a better search, or try again later." and the vendor's own error stays in the log, never in the listener's ear | A feed wobble must never be read out as "no matches", and a raw error is not something a listener can act on |
| Bedrock is on and fails, or invents a score | The failure is reported to the caller (a spoken decline); the listener's gap is **kept**, so asking again still works | Never a canned guess about a match the listener cannot see |
| Bedrock is off | The deterministic template, labelled `generated_by: template` | The fast tools never need a model |
| No match followed | `ToolError` with "tell me which game" | "Which match?" is a reasonable thing to be asked |
| Two matches fit | `ToolError` listing the options, remembered so a mispronounced answer can be resolved | Ambiguity is the listener's to settle |
| Unknown player | `ToolError` naming what was not found | Better than a confident wrong player |
| Unknown session | HTTP 404 | Tells the client to re-initialize rather than retry forever |

The distinction that matters: **protocol errors** are JSON-RPC errors; **tool failures** are successful responses
with `isError: true` and something the listener can actually hear. Confusing the two is the most common way an
MCP server becomes unusable in a voice context.
