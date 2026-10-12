# Tool contracts

## Descriptions are product surface

Alexa+ reads the `description` field to decide which tool a spoken
sentence maps to. These are written **for the model**, not for us.

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

---

## The eight

### `follow_match`

Binds a listener to a fixture. Everything afterwards needs no context —
a blind listener asking "what did I miss" in the 78th minute should not
have to say which game.

Side effect: following a match is what tells the poller to watch it.

Ambiguity is the listener's to resolve, not ours to guess. Two Arsenal
matches today returns a `ToolError` naming both, which Alexa+ reads as a
question.

Switching fixture resets `last_told_at`. Carrying it across would make
the first catch-up read out the wrong game.

### `get_match_state`

Score and clock. The most-asked question, so the fastest path: no
Bedrock, template only, target under 300 ms.

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

The spoiler guard, and the tool with the most interesting history.

Streams run 20-45 seconds behind the pitch; data feeds arrive in 5-15.
Without correction we know about a goal before the listener's television
shows it, and telling a blind fan about it makes us the thing that
ruined the match.

**The first version asked them to read the clock on their screen.** They
cannot see the clock - that is the premise of the entire product. It was
a guard that required sight to arm.

Three ways in now, in order of trust:

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
