# Accessibility rules

This is a product for people who cannot see a screen. Rules we hold
ourselves to, and the reasoning. The reasoning is ours; **it is not drawn
from user research or cited sources**, and no blind or low-vision person has
used the product. Where an automated test pins a rule it is named.

| Rule | Pinned by a test? |
|---|---|
| 1 nothing essential only on screen | by convention and review; not generally tested |
| 2 lead with the fact | phrasing checked in `tests/test_language.py` |
| 3 goals before chronology | `tests/test_language.py` |
| 4 minutes said as people say them | `tests/test_language.py` |
| 5 never repeat, never skip | `tests/test_what_did_i_miss.py` |
| 6 refusals are spoken | `tests/test_tools.py` |
| 7 speed | the fast tools call no model (`get_match_state`); a Bedrock catch-up takes about two seconds (README) |
| 8 never ask them to look | `tests/test_routing_phrases.py`, `tests/test_broadcast_sync.py` |
| 9 fail safe | `tests/test_broadcast_sync.py` |

## Where a listener's voice goes

Speech in is the most sensitive data this product touches, and who hears it
depends on the setting: **Groq Whisper** (only when `GROQ_API_KEY` is set, and
then first in the order because it measured best) sends it to Groq; **Amazon
Nova Sonic** keeps it in the AWS account; the **browser's
recognition** sends it to the browser vendor (Chrome and Edge, to theirs).
Nothing is stored by Sideline. With no Groq key nothing leaves AWS **unless live
captions are on** (`SIDELINE_LIVE_CAPTION`, default `browser`): the page then also
runs the browser's recognition to type words while you speak, which sends that
audio to the browser vendor. Set it to `off` for a strictly in-account path. A person
choosing a speech provider should be told where their voice goes, so say so in
any demo that uses one. We chose accuracy over keeping audio in-account only
because Groq is opt-in by key; if that trade is wrong for your users, leave the
key unset and Nova Sonic is first. See [SPEECH.md](SPEECH.md).

## Understanding mispronounced answers

A listener who cannot see the screen cannot catch a wrong guess, so when Sideline
offers a choice and the answer is only close to one option it resolves to the
nearest, and says what it understood. When two options are about equally near it
asks again rather than picking one. See [SPEECH.md](SPEECH.md).

## 1. The screen is never the only place a fact lives

Tools declare a UI resource in `_meta` (the MCP Apps pattern, which the
Alexa+ QuickStart mentions as optional): `get_match_state` a scoreboard
card, `get_lineups` the eleven, catch-up a timeline. **Whether any Alexa+
client renders these is unverified**; no participant can reach one.

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

Nobody asks "what happened in the forty-fifth minute plus two". (This is
a judgement about speech, not a measured one.)

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

A sighted viewer takes in the score at a glance.
The listener's equivalent has to be quick. The template tools make no model call, so the score, line-ups and
officials come back as fast as the feed's 12-second cache allows. Alexa+'s QuickStart sets a 500 ms round-trip
target. A Bedrock-composed catch-up takes about two seconds (a few samples on one account), so it misses that
target; that is stated, not hidden.

This is why `get_match_state` never calls a model. See
[BEDROCK.md](BEDROCK.md).

## 8. Never ask them to look at something

A spoiler guard that requires sight to arm is not a spoiler guard.

`sync_broadcast_delay` therefore does not ask the listener to read a clock.
What a blind listener has is their ears. The broadcast is audible and
contains moments both they and we can identify: kick-off, half time, a goal
going in. They say what they just heard; we know when it happened in the
data; the difference is the delay.

`tests/test_routing_phrases.py` asserts the tool description leads with
hearing, and `tests/test_broadcast_sync.py` asserts the refusal text never
mentions a clock.

The general rule: **before adding any input, ask what it requires of the
listener.** If the answer involves looking at anything, it is the wrong
input. The simulator follows it: one button once (a browser will not open a
microphone without a gesture), then hands-free.

## 9. Fail safe, not fast

Uncalibrated does not mean zero delay, which would spoil by default. It
means a conservative prior (45 s by default, or a regional figure from
`sideline/sync.py`; both are **our estimates**, not measurements of any
service), tightened by the first audio anchor. The cost of a too-high prior
is being a few seconds slow; the cost of zero is a spoiled goal.

## 10. The listener is in control

Sideline does not narrate. It answers.

Alexa+'s docs do not say whether a server may speak first (FL-04), so the
design assumes it cannot. We also think a listener who can ask when they
want is better served than one narrated at over the broadcast; that is a
hypothesis nobody has tested with a listener. We would still like the
option (FR-01 in FEATURE_REQUESTS.md).

## What we have not done

Stated plainly, because a judge will ask.

- **No testing with blind or low-vision users.** The design rests on how a
  broadcast presents information and on our own reasoning. The single most
  valuable next step is sitting with one person and one match.
- **English only in practice.** `translate()` exists and is wired into the
  catch-up, but no language other than English has been checked by a
  speaker for correctness or register, and it has never been called against
  Bedrock.
- **No screen-reader path for the companion simulator.** The simulator is
  a developer tool, not part of the product, but it should still be
  navigable and currently is not fully.
