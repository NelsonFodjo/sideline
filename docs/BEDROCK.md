# Amazon Bedrock

## The fair challenge

Alexa+ already contains a language model. Why call another one?

**Because Alexa+ only ever sees what we return.** Any reasoning that has to happen *before* the response leaves
our server has to happen on our server.

The catch-up is exactly that case. Eleven minutes of a match can hold nine raw events. Returning nine lines
hands Alexa+ a list, and a list read aloud sounds like a spreadsheet. Compressing nine events into one paragraph
that *leads with the goal* is a judgement about what mattered, and it has to be made here, because once we
return, it is too late.

## Where it is used, and deliberately not

**Used**

| Call | Why a model is needed |
|---|---|
| `catchup()` | Composition and prioritisation. The one that genuinely earns it. |
| `milestones()` | A long absence, compressed to headlines plus an offer of detail. Called by `what_did_i_miss`. |
| `translate()` | The same facts in another language or register (a listener can ask for one). |
| The voice agent, `/agent/chat` | Nova receives the MCP tool definitions, selects tools, and phrases the result. |
| Nova 2 Sonic | speech in: a separate use of Bedrock, described in [SPEECH.md](SPEECH.md). |

**Deterministic, never a model**

| Tool | Why |
|---|---|
| `get_match_state`, `get_officials`, `get_lineups`, `get_event_detail` | These are facts. Generating a scoreline adds latency and risk and improves nothing. |

That split is a latency decision as much as a quality one.

## One rule for failure

If Bedrock is **on** (`SIDELINE_BEDROCK=on`, or `auto` with AWS credentials), a failure is **reported** and never
papered over with canned wording:

- a call that errors or times out raises `BedrockUnavailable` (not retried: a retry costs another timeout);
- text that comes back empty or with a wrong score is refused, **retried once** (it is quick and often not
  repeated), and then raises `BedrockUnavailable`;
- the `what_did_i_miss` tool turns that into a spoken decline ("The language model said: <the real error>. Try again shortly", or earlier wording: "I can't put that into words right now, ask me
  again in a moment") **without moving the listener's marker**, so asking again still gets the whole gap;
- the voice agent surfaces it as "no answer".

If Bedrock is **off**, the deterministic templates in [`templates.py`](../sideline/language/templates.py) are used,
and the response says `generated_by: template`. That is a configuration choice, not a fallback.

Every response reports who wrote the words in `structuredContent.generated_by`: `bedrock`, `template`,
`tool-data` (the agent asked for facts) or `bedrock+bedrock` (translated). It is the easiest way to show the model
working on camera.

## The grounding rule

This is the most important paragraph in the repository.

```
Use ONLY the data given to you. Never add a detail that is not in it - no scorers, minutes, reasons
or context from your own knowledge of the sport. If something is not in the data, it did not happen.
```

A product whose entire claim is *"it knows what is happening right now"* is destroyed by one confidently invented
goal. Full prompts: [`language/prompts.py`](../sideline/language/prompts.py).

### The guard

Prompting is necessary but not sufficient, so there is a check as well. `_score_consistent()` parses any
scoreline in the generated text and refuses the whole output if it disagrees with ours (`BedrockUnavailable`, so
the listener is told, not given a wrong score). It is deliberately conservative: it only refuses when the text
states a parseable scoreline **and** it disagrees. Vague text passes.

## Latency

> **Alexa+'s QuickStart sets a round-trip target of 500 ms** (rules read 2026-10-12). **A Bedrock catch-up misses
> it:** a real Nova call took about 1.5 to 2.1 s on 2026-10-13 (a few samples on one account, not a guarantee). The
> fast tools call no model, so they are not held to account by this.

Three rules keep the rest inside a listener's patience:

1. Fast tools never touch Bedrock.
2. Catch-up prompts are capped at 12 events.
3. The provider caches for 12 seconds, so no tool waits on the football feed more than once.

`max_attempts=1` on the boto3 client is intentional: a retry costs another request timeout. The request ceiling is
8 seconds. A first-ever precompute-and-cache design was built and then removed: it moved the model off the
listener's clock but was only ever tested against a simulated model, and the honest statement is that a catch-up
takes about two seconds.

## The voice agent

The simulator posts the listener's transcript to `/agent/chat`. The server first resolves what they meant
([SPEECH.md](SPEECH.md)), then gives Nova the public MCP tool names, descriptions and input schemas through
Bedrock Converse tool use. When Nova picks a tool, the call goes through
[`mcp/client.py`](../sideline/mcp/client.py) to this server's own `/mcp` endpoint, so it crosses the real protocol
(session, `tools/call`, schema validation) exactly as an external client's would. The result goes back to Nova for
a short, grounded reply.

Conversation context is four layers, each small and bounded, and none is persisted across restarts:

1. **Recent turns**: the last 12 messages per listener, 30-minute idle expiry, 256 listeners at most.
2. **The topic** (`Focus` in `agent.py`): after each turn the real tool results, not the model's wording, are reduced to
   the match, team and player just discussed, and the next turn's system prompt says so ("The listener was last talking
   about the match Arsenal against Lille, the player Saka..."). That is what makes "and their form?", "what about him?"
   and "that match" mean something on a small model, including for a match the listener is not following. It expires
   after ten minutes, a new match drops the old player, a bare pronoun is never a topic, and the prompt says it is
   context, not a fact to state.
3. **Offers** (`resolve.py`): what was just offered ("Arsenal or Arsenal W?") is remembered for two minutes, so a
   mispronounced or one-word answer snaps to an option.
4. **The interruption**: if the listener talked over the last answer, the words that were cut off are passed along so
   what they say next is read as a follow-up to them.

The durable context, which team is followed, what has been told (`last_told_at`), the broadcast delay, favourites and
time zone, lives in the state store and survives restarts. The model never receives AWS credentials. The agent is told to answer in at most two
short sentences, never to narrate, and never to promise to keep the listener updated (the server cannot speak
first).

For the agent, `what_did_i_miss` returns its structured event facts, not a prewritten paragraph (a header asks for
this): Nova is itself a model and would only paraphrase a paragraph, at the cost of a second model call.

## Model choice

`amazon.nova-micro-v1:0` is the default, set by `SIDELINE_BEDROCK_MODEL`. It supports the Converse API used for
both tool use and catch-up generation. This is compression under a voice deadline, not writing, so a small fast
model with `temperature=0.2`. Availability varies by account and region; `make aws-check` checks the selected
model. We make no claim about what model Alexa+ uses.

**A larger model, measured (2026-10-13, one account, one run each, so indicative only).** Asked a broad batch of
real questions against the live feed, Nova Micro dropped arguments the question plainly gave: "where is Celtic in the
league?" and "who are the top scorers for Rangers?" arrived with no team, and "what did I miss?" after following a match
went to the wrong tool. `amazon.nova-lite-v1:0` kept the team in both and chose the right tool for the third. On the
71-phrasing routing check Micro scored 71 and Lite 70 (the one miss was a transient `AgentUnavailable`, not a routing
choice), and the whole run took 68 s against 88 s. So the voice agent is smarter and no slower on Lite; the default stays
Micro because the latency and caching figures in these docs were measured on it. Switching is one line:
`SIDELINE_BEDROCK_MODEL=amazon.nova-lite-v1:0`. Prompt caching on Lite was not tried.

## Turning it on

Step by step in [AWS_SETUP.md](AWS_SETUP.md). Model access is granted per account and model, and an access failure
can look like a credentials error; `make aws-check` separates the two.

```bash
pip3 install boto3
# set AWS credentials in .env, and Bedrock switches on by itself (SIDELINE_BEDROCK=auto)
make aws-check
```

## IAM

What the Bedrock code calls (the full policy, with Polly and DynamoDB, is in [AWS_SETUP.md](AWS_SETUP.md)):

```json
{"Effect": "Allow",
 "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream",
            "bedrock:InvokeModelWithBidirectionalStream"],
 "Resource": "arn:aws:bedrock:*::foundation-model/amazon.nova-*"}
```

The agent uses `InvokeModel` or the streaming call; the catch-up uses `InvokeModelWithResponseStream`; Nova Sonic uses
the bidirectional stream. No `bedrock:*`.

## Cost

Not measured. A catch-up sends a few hundred tokens of event JSON and asks for at most 160 back, and a listener is
expected to ask a handful of times per match; those are expectations, not observations. Set a budget alarm before
turning it on and read your actual usage after the first run.

## Token usage

Every model call writes a `tokens` line to the day's call log (`logs/calls-<date>.jsonl`) with the input and output
counts exactly as Bedrock reports them (the Converse response's `usage`), and `make log-report` totals them by source
(`agent` for the voice agent, `text` for catch-ups). Measured on the real service with all 27 tools offered: about
5,000 input tokens and 15 to 20 output tokens for a one-tool question. Nearly all of the input is the tool list, which
is the price of offering 27 tools; `SIDELINE_AGENT_TOOLS=core` offers 11 and cuts it roughly in half.

## Why replies are fast, and five things that keep the small model honest

Measured on the real service, on questions about a real team (2026-10-14): a follow-up answered in 0.8 to 1.0 s and a
first question in 3 to 5 s (the first includes cold connections and the feed).

- **Short, finished answers are not rephrased.** Nearly every tool already writes its answer for the ear. Asking the model
  to say it again in its own words costs a whole round trip (about a second and a half) and can only make it less exact. So
  when one tool answered one question and its text is 240 characters or fewer, it is returned as written
  (`generated_by: tool`). Longer answers (a full line-up) still go through the model, which shortens them for the ear, unless
  the tool marks its answer `verbatim` (`get_match_report`, whose goals a rewrite would drop, up to 900 characters). Tools
  whose agent-mode output is facts to be phrased (`what_did_i_miss`) always go through the model, and so does a listener who
  asked for brief answers.
- **The model is told today's date**, in the listener's own zone. Left to guess, it wrote last year ("20 September" became
  2025) and the match was "not found". The finder also moves a date written with the wrong year to the year nearest to now.
- **Arguments the question gives away are filled in.** A small model drops optional arguments first: asked "who came on?" it
  called `get_match_report` with no `part`, and the whole report was read out again. Where the words of the question say
  it (came on, cards, scored, VAR), `part` is set in code, never overriding what the model passed.
- **A competition the listener did not say is dropped.** Asked "what are the next matches?" the model passed "Premier League",
  copied from an example in a tool description, for a feed that does not cover it. A competition stays only if one of its
  words is in the question (`_without_invented_competition`). With none, the tool asks which, and names the leagues the
  feed does cover.
- **The match they were just asking about is remembered** for ten minutes (`rec["discussed"]`), so "who came on?" after
  "what happened in the last Celtic match?" needs no match named. A match is never picked that they did not ask about, and
  a list of matches read out for a choice remembers the question, so the pick answers it ([FINDER.md](FINDER.md)).

**Where the time goes, and what was done** (measured 2026-10-14, a warm server): a model call is about 0.75 s with 7,800 input
tokens, nearly all of it the tool list; a feed lookup is 0.5 to 1 s each; speech for a long answer is 2.5 to 2.8 s. So
the speech is pipelined a sentence at a time (first audio 1.2 s: [SPEECH.md](SPEECH.md)), the squad and manager requests
run in parallel, and the model is called once at startup so the connection and TLS handshake are the server's, not the
first listener's (the first question went from 5.5 s to 3.4 s). **Prompt caching was tried and does not apply here**: Nova
Micro rejects a `cachePoint` in the tool list ("extraneous key [cachePoint]"), and the tool list is the bulk of the prompt,
so there was nothing worth caching.

Routing is held at 71 of 71 on `make route-check` with all 27 tools offered, by descriptions that each name their neighbour
("not the table (get_standings)"). It took three passes: a longer prompt and more tools made follow, preview and standings
phrasings slip, and each was fixed at the description that attracted it, not by adding rules. A shortlist of tools offered
to the model was tried first and rejected on its recall: [FINDER.md](FINDER.md), "Tried and rejected".
