# Tool contracts

## Descriptions are product surface

A client reads the `description` field to decide which tool a sentence
maps to; the Alexa+ Design Guide says descriptions should state when to
call the tool and what it returns. These are written **for the model**,
not for us. We have not observed Alexa+ itself routing; our test checks our
own wording.

Three rules applied throughout `registry.py`:

**1. Lead with intent, not implementation.**

> good — "What the listener missed while they were away."
> bad — "Returns events between last_told_at and now."

**2. Include the phrasings listeners actually use.**

People say "what did I miss", "what happened", "catch me up", "did I miss
anything", "I just got back", "fill me in". All of those must land on the
same tool. `tests/test_routing_phrases.py` asserts they are still in the
description, because this is what breaks silently when somebody tidies
the wording.

**3. Say what a tool does *not* do, when two are close.**

`get_match_state` and `what_did_i_miss` compete for the same utterances.
Without explicit disambiguation in *both* descriptions, routing becomes a
coin toss. The test asserts each one names the other.

**4. Fix routing in the descriptions, not in the agent.** Real Alexa+ sees only this MCP server: its tool names,
descriptions, schemas and results. A patch inside the voice agent would make the simulator look better and change nothing
for Alexa+. So a misroute is fixed here. Example: "let's look at the Superliga" went to `get_competitions` every time,
because that tool's description said "do you have La Liga" and a small model took any league name for it. The fix was to
say what the tool is *not* for and to give `get_fixtures` that phrasing. A related finding: **the example phrases in a
description are copied by a small model** (it passed "Premier League" for a feed that does not cover it), so examples are
chosen with care. The agent keeps only small safety checks on arguments the model invents (an id, a competition the
listener never said), which are pinned in `tests/test_agent.py`.

---

## The tools

### `follow_match`

Binds a listener to a fixture. Everything afterwards needs no context —
a blind listener asking "what did I miss" in the 78th minute should not
have to say which game.

Side effect: following a match is what tells the poller to watch it.

Ambiguity is the listener's to resolve, not ours to guess. Two Arsenal
matches today returns a `ToolError` naming both, which Alexa+ reads as a
question.

Following works for a match days away (a team's next match is followed and said to be not started; the poller waits), and `stop: true` stops following ("stop following"). Following a match also makes it the one they mean next.

Switching fixture resets `last_told_at`. Carrying it across would make
the first catch-up read out the wrong game.

### `get_match_state`

Score and clock. The most-asked question, so the fastest path: no
Bedrock, template only: no model call. Before kick-off it also says when the match starts ("Kick-off is
in 1 hour 56 minutes, at 11:45"), and the structured result carries a `clock` block (the time now, the
kickoff, minutes between). The clock is `sideline/clock.py`; spoken clock times are in the server machine's
local zone, which is the listener's when it runs on their machine.

**Does not advance `last_told_at`.** Hearing the score is not the same as
being told what happened. A listener who asks the score and then asks
what they missed must still get the goals. There is a test for this,
because it is exactly the kind of thing that gets "optimised" later.

### `get_lineups`

The graphic on screen for eight seconds before kick-off, never read
aloud. Listeners ask for it late and often.

Keeper first, then the rest — a listener building a mental picture needs
the shape, not an alphabetical list.

Advances `last_told_at`: we spoke to them about this match at this
minute, so the catch-up window should start here.

### `what_did_i_miss`

The headline.

```
1. gap_for()            events since last_told_at, minus already-told
2. bedrock.catchup()    compress to one paragraph, or template
3. mark_told()          move the marker, record the event ids
```

Step 3 is the one people forget. Without it the listener hears the same
goal every time they ask.

A goal later overturned by VAR is still reported, flagged as disallowed.
A listener who heard the crowd go up needs to know it was chalked off; a
deleted row cannot tell them anything.

`since_minute` exists only for explicit phrasing — "since half time".
Normally omitted, and the schema description says so, so the model does
not helpfully invent one.

### `get_event_detail`

Live commentary never lets you go back. A listener who half-heard a goal
while the kettle was on has no way to retrieve it.

Resolution order: explicit id, then nearest minute, then most recent of a
kind. **Nearest**, not exact — listeners say "that goal around the half
hour" and are usually a minute or two out.

`kind` is per sport (`goal`, `card`, `substitution`, `var` in football;
`basket`, `foul`, `timeout`, `ejection`, `review`, `substitution` in
basketball), plus `score`, which means whatever scores in this sport, so
"that goal" and "that basket" resolve the same way. See [SPORTS.md](SPORTS.md).

### `get_officials`

Named once in a pre-match graphic and then effectively unavailable for
two hours. Cheap, and the thing blind fans mention first when asked what
they cannot find out.

If the provider gives no running card count we derive it from our own
event log. We have the cards; there is no reason to make the listener go
without.

### `get_player_context`

The on-screen caption, spoken.

Matching is fuzzy on purpose. Listeners say surnames, mispronounce
names, and transcription is imperfect. Exact matching would fail
constantly on precisely the names that matter.

### `sync_broadcast_delay`

The spoiler guard.

The design assumes streams run behind the pitch by tens of seconds and
data feeds by less (figures such as 20-45 s and 5-15 s are our assumptions;
no stream or feed was timed here).
Without correction we know about a goal before the listener's television
shows it, and telling a blind fan about it makes us the thing that
ruined the match.

**It does not ask them to read the clock on their screen.** They cannot
see it, which is the premise of the product; a guard that requires sight to
arm is no guard.

Three ways in, in order of trust:

1. **Audio anchor.** "Kick-off just went", "that's half time", "they've
   just scored". The listener names a moment they heard; we know when it
   really happened. Needs no sight and nobody's help.
2. **Sighted companion.** In a viewing centre there are people around.
   Legitimate, but a fallback - requiring it would make the guard depend
   on someone being there.
3. **Regional prior.** Armed at `follow_match` from the device locale,
   so we never spoil before anyone has said anything.

Goal anchors measure on the **wall clock**, using the moment the poller
logged the event. Period anchors fall back to minute arithmetic and
carry up to a minute of uncertainty - which is why a goal anchor is
preferred and why the full-bucket conservatism was reduced to the
midpoint.

The offset is applied once, in `resolve_fixture()`, so no other tool has
to know any of this happened.

### `get_fixtures`

What is on, for a listener who has not named a team: "which teams are playing", "what's live", "any Premier
League tonight". Up to five matches, **each with its time** in the listener's own clock (or its minute if it is
under way), live ones first, then the big competitions, then the rest, and a count of the remainder. On a quiet day it says so and names the next day with matches (looking up to ten days ahead, one cached request each), so "the next matches" is never answered with "nothing tomorrow". It reads the
day's list the server already keeps, so it costs no extra feed request. Every place Sideline names a match, in a
list, in "which one?", and in "did you mean?", carries the time, because for a match the time is what the listener
is asking about.

### `get_match_preview`

What a friend says before the game: who is hosting whom and in which competition, where it is played, when it
starts **in the listener's own clock**, the weather at the ground, how each side lines up, and who the data
vendor's model favours. Every part is a real fact or left out and named in `missing`; nothing is guessed, and no id
is ever said. Times use the zone the page reports (its offset and its name) and are said the way people say them: "10 PM Mauritius
time", "5 PM US Eastern time", "8 PM India time". With no zone known they are UTC, said as such.

The football feed has no weather, so a city and country go to [Open-Meteo](https://open-meteo.com/) and are
accepted only when the country matches (a Hartlepool in another country is not used). `SIDELINE_WEATHER=off` keeps
that off the network. The estimate is the vendor's, labelled as an estimate, and is not advice.

Does not advance `last_told_at`: a preview is not news of what happened.

### Pointing any tool at any match

Every match tool (`get_match_state`, `get_lineups`, `get_officials`, `get_match_stats`, `get_injuries`, `get_event_detail`,
`get_player_context`, `get_head_to_head`, `get_match_preview`, `get_match_report`) accepts `team`, `opponent`, `when`
(`last`, `next`, `yesterday`, `today`, `tomorrow`) and `date` as well as `fixture_id`, so a match that is not the followed one,
a played one included, can be named. Which match is meant, and when to list the options instead of guessing, is
[FINDER.md](FINDER.md).

### The other sixteen: discovery, tables, numbers, people, you

Each is one intent, each names its neighbour in its description so routing never has to guess, and each is read-only
except the two that remember. All of them say what is missing instead of guessing it.

| Group | Tool | Notes |
|---|---|---|
| Discover | `search`, `get_competitions` | A heard name is checked against what exists; a free feed's few leagues are listed. |
| | `get_standings`, `get_top_scorers` | Pass `team` for one team's place or scorers (its league is found from its matches). Positions are said as words (first, second...). With no competition named, the followed match's is used; with a team named, its league is found from the team's own matches (so "how many points do Celtic have" needs no match followed); with neither, it asks which, listing the leagues the feed covers. |
| | `get_schedule` | A team's next matches with times (`which: next`) or its last results with scores (`which: last`), as far as the feed can see (six weeks ahead, three months back on the free plan). Owns "what time is X playing"; `get_match_preview` owns "tell me about the match". |
| Teams, with no match | `get_squad`, `get_team_stats`, `get_team_form` | Players by position with the manager and captain (a position gives the names); the season so far; the last results as won/drew/lost (pass `team`). None needs a match to be followed. |
| Played matches | `get_match_report` | The result and goals first, then cards, substitutions or VAR by name (`part`). Any match that has been played: the events come from the feed once and are kept. Returned as written. |
| The match | `get_match_stats`, `get_team_form`, `get_injuries` | The numbers, the last results as won/drew/lost, who is out and why. |
| People | `get_player_stats` | A player's season; `get_player_context` stays for what he just did. |
| You | `set_favourites`, `get_my_matches` | Only names the listener gave are stored. "Are my teams on" then needs no name. Nothing is pushed: Alexa+ cannot be spoken first. |
| | `set_preferences` | "Brief", "normal" or "full", and a language. The detail reaches the agent's instructions; the language is what `what_did_i_miss` already translates to. |
| Meta | `get_capabilities` | Read from the tools actually offered, so it is true for this feed. |

**Tools follow the feed.** `registry.TOOL_REQUIRES` maps a tool to the capability it needs, and a feed lists what it
has (`Provider.capabilities`). The server offers only the tools whose need is met, on `tools/list` and to the voice
agent alike. A feed that adds a capability gains its tools with no change to them. For a small model,
`SIDELINE_AGENT_TOOLS=core` offers only the core eleven.

### `get_head_to_head`

The least essential tool here, included on purpose. A product that only
answers urgent questions feels like a utility. The friend on the sofa
also says "we never beat them at their place."

---

## Return shape

Every tool returns `(spoken_text, structured, ui_payload)`.

- **`spoken_text`** — what Alexa+ reads. It may rephrase.
- **`structured`** — machine-readable detail. Includes `generated_by`,
  so anyone reading a response can see whether a model was involved in
  producing the words.
- **`ui_payload`** — the MCP Apps card for screened devices, or `None`.

**The rule that governs all of them:** nothing essential may live only in
the UI payload. A listener on a voice-only Echo must get the whole answer
in `spoken_text`. This is an accessibility product; a screen-only fact is
a bug. See [ACCESSIBILITY.md](ACCESSIBILITY.md).

---

## Errors

| Kind | Shape | When |
|---|---|---|
| `InvalidParams` | JSON-RPC error, -32602 | Argument failed schema validation |
| `MethodNotFound` | JSON-RPC error, -32601 | Unknown method |
| `ToolError` | Success, `isError: true`, spoken text | The tool ran but could not do the job |

The distinction matters. A tool that cannot find a fixture has not broken
the protocol — Alexa+ should be able to tell the listener so, rather than
see a transport failure and go silent.

Every `ToolError` carries a line written to be **spoken**:

```
"I'm not following a match yet. Tell me which game to follow."
"I can't find Saka in this match."
"I can see more than one Arsenal match today. Which one - ...?"
```

Not "fixture_not_found".
