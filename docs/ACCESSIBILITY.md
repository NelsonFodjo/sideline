# Accessibility rules

This is a product for people who cannot see a screen. Rules we hold
ourselves to, and the reasoning. The reasoning is ours; **it is not drawn
from user research or cited sources**. The team reports that one blind person has since
tried the product informally (see the limits below).
Where an automated test pins a rule it is named.

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
depends on the setting. The speech models, **Mistral Voxtral** and **Amazon Nova Sonic**, run on Amazon Bedrock and keep it
inside the AWS account; the **browser's recognition** sends it to the browser vendor (Chrome and Edge, to theirs).
Nothing is stored by Sideline. Nothing leaves AWS **unless live captions are on** (`SIDELINE_LIVE_CAPTION=browser`; the default
is `off`): the page then also runs the browser's recognition to type words while you speak, which sends that audio to
the browser vendor. Set it to `off` for a strictly in-account path. A person choosing a speech provider should be told
where their voice goes, so say so in any demo that uses captions. We started with a third-party recogniser because it
measured best, then found an AWS model that matched it and removed the third party, so that the default no longer asks a
listener to trade accuracy for privacy. See [SPEECH.md](SPEECH.md).

## Understanding mispronounced answers

A listener who cannot see the screen cannot catch a wrong guess, so when Sideline
offers a choice and the answer is only close to one option it resolves to the
nearest, and says what it understood. When two options are about equally near it
asks again rather than picking one. See [SPEECH.md](SPEECH.md).

## 1. The screen is never the only place a fact lives

Tool results carry the data a screen could draw (`_meta.sideline.ui`: a scoreboard for `get_match_state`, the eleven for
`get_lineups`, a timeline for catch-up, a table for `get_match_stats`). This is our own field, **not** an MCP Apps
resource: the server does not serve one, and whether any Alexa+ client would render it is unverified, since no
participant can reach one.

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
officials come back as fast as the feed and its cache allow (the scoreboard and a live match summary are kept for 5 s,
so the tools one question calls share one read). Alexa+'s QuickStart sets a 500 ms round-trip
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

The server does not narrate. It answers.

Alexa+'s docs do not say whether a server may speak first (FL-04), so the
server is designed on the assumption that it cannot: it never pushes. The
simulator page is a client, and it does read live commentary unprompted:
while a match is followed it asks for new lines every 12 s and reads them,
never over the listener, and "stop commentary" ends it. Whether a listener
prefers that to asking when they want is a hypothesis nobody has tested
with a listener. We would still like the option for a server to speak
first (FR-01 in FEATURE_REQUESTS.md).

## 11. Aids for the listener who is not looking

In the simulator, **not yet tried on a real device**:

- **Tones.** A short one when a question has been heard, another for a problem, one when a stop word cut her off. Settings
  turns them off.
- **Speech speed.** 0.85× to 2× in Settings, or say "speak faster", "slow down", "normal speed".
- **Asked by voice, answered on the page:** "say that again", "spell that", "carry on" after an interruption, and
  "what can you do?".
- **Scores and minutes spoken as people say them** (`voice.speakable`): "3-2" is "3 to 2", "73'" is "73rd minute".
- **Microphone problems are said aloud** (`warnAloud`), not only written.

## What we have not done

Stated plainly, because a judge will ask.

- **One informal session with a blind listener, reported by the team.** A real microphone, spoken
  questions and spoken answers. It is one person, with no notes or measurements kept, so it is an
  encouraging first sign and not evidence; the next step is wider listening across a full match and
  more people.
- **English only in practice.** `translate()` exists and is wired into the
  catch-up, but no language other than English has been checked by a
  speaker for correctness or register, and it has never been called against
  Bedrock.
- **No screen-reader path for the companion simulator.** The simulator is
  a developer tool, not part of the product, but it should still be
  navigable and currently is not fully.
