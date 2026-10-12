# Accessibility rules

This is a product for people who cannot see a screen. Rules we hold
ourselves to, and the reasoning. These are testable claims, not posture.

## 1. The screen is never the only place a fact lives

Alexa+ supports the MCP Apps extension, and we use it: `get_match_state`
returns a scoreboard card, `get_lineups` returns the eleven, catch-up
returns a timeline.

**But every one of those facts is also in `spoken_text`.** The card is an
enhancement for a sighted person in the room — a partner, a child, a
carer — and never a substitute.

Easy to get wrong, because a card looks better in a demo video.

## 2. Lead with the fact

The listener has one ear on the television. Every clause before the
answer costs them whatever is happening on the pitch.

> **"Saka scored on 34"** — not *"So, there's been quite a bit of action.
> Let me fill you in. In the 34th minute, Bukayo Saka..."*

No preamble, no sign-off, no "Sure! Here's what you missed."

## 3. Goals before chronology

The template catch-up deliberately reorders: goals first, regardless of
when they happened.

A naive implementation returns events in time order and buries a goal
behind a substitution. The listener wants the score change first. This is
in `templates.say_catchup()` and in the Bedrock prompt, so both paths
behave the same way.

## 4. Minutes said the way people say them

`45+2` becomes **"just before half time"**. `90+4` becomes **"deep into
stoppage time"**.

Nobody asks "what happened in the forty-fifth minute plus two".

## 5. Never repeat, never skip

`last_told_at` plus `told_event_ids` exist so a listener is told each
thing exactly once.

Repeating is worse than silence — it makes them distrust everything else
the system says. Skipping is worse still: they find out from the crowd.

## 6. Refusals are spoken, not coded

Every failure the listener can reach carries a sentence a person would
say. `"I can't find Saka in this match."` — not `player_not_found`.

A blind listener cannot see an error state. If it is not sayable, it does
not exist for them.

## 7. Speed is an accessibility requirement

A sighted viewer glances at the screen in 200 ms. Our budget for the same
information is under 300 ms for fast tools and under 2.5 s for a
catch-up.

This is why `get_match_state` never calls a model. See
[BEDROCK.md](BEDROCK.md).

## 8. Never ask them to look at something

A spoiler guard that requires sight to arm is not a spoiler guard.

We built one. The first version of `sync_broadcast_delay` asked the
listener to read the clock on their screen so we could work out how far
behind their broadcast was. Every test passed. The feature was useless
to the only person it was for.

What a blind listener has is their ears. The broadcast is audible, and
it contains moments both they and we can identify - kick-off, half time,
a goal going in. They say what they just heard; we know when it really
happened; the difference is the delay.

`tests/test_routing_phrases.py` now asserts the tool description leads
with hearing, and `tests/test_broadcast_sync.py` asserts the refusal
text never mentions a clock. The mistake cannot come back quietly.

The general rule: **before adding any input, ask what it requires of the
listener.** If the answer involves looking at anything, it is the wrong
input, however well it works.

We then made the same mistake again in the simulator, which shipped with
push-to-talk, suggestion chips and a text box. All three require sight.
It is now hands-free: one button once, because a browser will not open a
microphone without a gesture, and nothing after that.

Twice is a pattern, which is why the rule is written here rather than
left as a lesson learned.

## 9. Fail safe, not fast

Uncalibrated used to mean zero delay, which meant spoiling by default.
Now it means a conservative regional prior, tightened by the first audio
anchor. The worst uncalibrated case is being a few seconds slow. The
worst case at zero was ruining the match.

## 10. The listener is in control

Sideline does not narrate. It answers.

That started as a platform constraint — Alexa+ owns the turn model, so we
cannot speak first. It turned out to be the right design anyway. Blind
fans watch with a sighted friend they *interrupt*; they do not want a
second commentator talking over the first.

We would still like the option. See [PRODUCT_FEEDBACK.md](PRODUCT_FEEDBACK.md).

## What we have not done

Stated plainly, because a judge will ask.

- **No testing with blind users yet.** The design follows published
  accounts of how blind fans watch football and the structure of
  broadcast information, not our own user research. The single most
  valuable next step is sitting with one person and one match.
- **English only in practice.** `translate()` exists and is wired, but
  only English has been checked for register.
- **No screen-reader path for the companion simulator.** The simulator is
  a developer tool, not part of the product, but it should still be
  navigable and currently is not fully.
