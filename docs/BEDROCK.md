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
| The Claude MCP host, `/agent/chat` | Fetches `initialize` instructions and `tools/list` over MCP, gives Claude the live tool catalog, then executes Claude's `tools/call` selections over MCP. |
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
`tool-data` (the host asked for facts) or `bedrock+bedrock` (translated). It is the easiest way to show the model
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
> it:** a real Bedrock Converse call took about 1.5 to 2.1 s on 2026-10-13 (a few samples on one account, not a guarantee). The
> fast tools call no model, so they are not held to account by this.

Three rules keep the rest inside a listener's patience:

1. Fast tools never touch Bedrock.
2. Catch-up prompts are capped at 12 events.
3. The provider caches for 12 seconds, so no tool waits on the football feed more than once.

`max_attempts=1` on the boto3 client is intentional: a retry costs another request timeout. The one exception is the Bedrock MCP host, which retries **once**, after 0.6 s, when AWS answers at once with "capacity limit reached" or "slow down" (`ServiceUnavailableException`, `ThrottlingException`): that refusal is quick and the same request a moment later usually works. Any other error is not retried. The request ceiling is
8 seconds. A first-ever precompute-and-cache design was built and then removed: it moved the model off the
listener's clock but was only ever tested against a simulated model, and the honest statement is that a catch-up
takes about two seconds.

## The Claude MCP host

The simulator posts the listener's transcript to `/agent/chat`. The server resolves what they meant
([SPEECH.md](SPEECH.md)), then discovers the MCP `initialize` instructions and `tools/list` catalog over
[`mcp/client.py`](../sideline/mcp/client.py). It passes the complete discovered descriptions and input schemas
to Bedrock Converse up front. Claude decides whether and what to call; selected tools are executed through the
same server's `/mcp` endpoint, with protocol sessions and server-side schema validation. Tool results return to
Claude for its answer. The prompt contains general grounding and spoken-response guidance, not phrase-to-tool rules.

Bedrock is a model API, not an MCP client: a host must do this discovery and dispatch. Any other
MCP-capable host can connect directly to `/mcp` and provide Claude (or another model) with the same tool catalog.

Conversation context is four layers, each small and bounded, and none is persisted across restarts:

1. **Recent turns**: the last 12 messages per listener, 30-minute idle expiry, 256 listeners at most.
2. **The topic** (`Focus` in `agent.py`): after each turn the real tool results, not the model's wording, are reduced to
   the match, team and player just discussed, and the next turn's system prompt says so ("The listener was last talking
   about the match Arsenal against Lille, the player Saka..."). That is what makes "and their form?", "what about him?"
   and "that match" mean something on a model, including for a match the listener is not following. It expires
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

For Claude, `what_did_i_miss` returns its structured event facts, not a prewritten paragraph (a header asks for
this): Claude is itself an LLM and would only paraphrase a paragraph, at the cost of a second model call.

## Model choice

`us.anthropic.claude-sonnet-4-5-20250929-v1:0` is the default, set by `SIDELINE_BEDROCK_MODEL`. It supports Bedrock's Converse API used for
both MCP tool use and catch-up generation. Anthropic Claude delivers exceptional tool routing precision, strict zero-hallucination discipline, and natural conversational phrasing. Availability varies by account and region; `make aws-check` checks the selected
model. We make no claim about what model Alexa+ uses.

**Historical comparison (2026-10-13, one account, one run each; not a measurement of the current MCP-discovery prompt).** Asked a broad batch of
real questions against the live feed, Nova Micro dropped arguments the question plainly gave: "where is Celtic in the
league?" and "who are the top scorers for Rangers?" arrived with no team, and "what did I miss?" after following a match
went to the wrong tool. `amazon.nova-lite-v1:0` kept the team in both and chose the right tool for the third. On the
71-phrasing routing check Micro scored 71 and Lite 70 (the one miss was a transient `AgentUnavailable`, not a routing
choice), and the whole run took 68 s against 88 s. So the voice agent is smarter and no slower on Lite; the default stays
Micro because the latency and caching figures in these docs were measured on it. Switching is one line:
`SIDELINE_BEDROCK_MODEL=amazon.nova-lite-v1:0`. Prompt caching on Lite was not tried.

A second batch of about fifty harder questions (misspelt and misheard names, named days and dates, "who got booked in the Celtic
Rangers game", "keep answers brief", gibberish, other sports) agreed: **Micro** left out arguments the question gave (a date, a
team, a table's team) in roughly a third of them, and sent "keep answers brief" to a match preview. **Lite** passed dates and
"brief" correctly and was the better agent on all but a few. Neither answers a question about two teams at once ("Celtic or Rangers,
who is higher?") because it needs two tool calls. If your account allows it, Lite is the one to run.

## Turning it on

Step by step in [AWS_SETUP.md](AWS_SETUP.md). Model access is granted per account and model, and an access failure
can look like a credentials error; `make aws-check` separates the two.

```bash
./run.sh
# On first launch this installs boto3 in .venv from requirements.txt.
# Set AWS credentials in .env and Bedrock switches on by itself (SIDELINE_BEDROCK=auto).
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
Every turn now receives the current tool catalog from MCP, without the old shortlist option or phrase-to-tool instructions.
The simulator's fake-model tests verify that the full catalog, tool schemas, tool execution and post-tool results are wired
through the protocol. **Real-Nova routing with this new path has not yet been re-measured**; `make route-check` is
available to test it against the live model and invented match data.
