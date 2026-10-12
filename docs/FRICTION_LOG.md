# Friction log

> Optional: the task you attempted, the steps you took, what you expected
> vs. what actually happened, a severity rating, any workaround you used,
> and an actionable suggestion. Submissions with friction logs can earn up
> to a 10% judging bonus.

Recorded as we hit them, not written up at the end. Severity:
**critical** blocks shipping · **important** costs real time ·
**nice-to-have** rough edge.

## Summary

| # | Task | Expected vs actual | Severity | Workaround | Suggestion |
|---|---|---|---|---|---|
| FL-01 | Confirm "what did I miss" routes to the right tool | Expected a CLI utterance preview; found none — the only way to know is a round trip through a device | important | Phrase-assertion test over our own descriptions | Ship `alexa-ai test-utterance` |
| FL-02 | Tell a listener a goal has gone in, unprompted | Expected either a push mechanism or an explicit statement there is none; inferred it from absence | critical | Redesigned around on-demand questions | State the constraint in the MCP Toolkit overview; add opt-in push |
| FL-03 | Write nine tool descriptions that route reliably | Expected documented patterns; found none | important | Three rules of our own, at the top of `registry.py` | Publish a tool-description guide, incl. the adjacent-tool problem |
| FL-04 | Keep catch-up inside a 3 s voice budget | Expected interactive-friendly defaults; default retries can exceed the whole interaction | important | `max_attempts=1`, 3 s read, 1 s connect, template fallback | Document a low-latency Bedrock preset |
| FL-05 | Keep the *first* catch-up of a match in budget | Expected consistent latency; first invoke after idle is noticeably slower | nice-to-have | Template fallback absorbs it | Document the behaviour and a warm-up pattern |
| FL-06 | Return a UI payload plus per-tool timing without collisions | `_meta` is open; no conventions exist | nice-to-have | Namespaced `_meta.sideline` | Register conventional `_meta` keys, or recommend reverse-DNS |
| FL-07 | Poll a live match every 15 s on a free tier | Expected one usable free tier; all are delayed or capped around 100 calls/day against the ~360 needed | important | StatsBomb Open Data + deterministic replay harness | For organisers: publish data sources with usable free tiers |
| FL-08 | Share a private repo with reviewers | Documented 7-day expiry, but the instinct is to invite early | nice-to-have | Checklist item: invite on submission day only | Surface the expiry next to the repo URL field in the form |
| FL-09 | Stop the agent spoiling a goal the viewer's screen hasn't shown | Expected the desync to be a known voice-sports problem; found nothing | important | `sync_broadcast_delay` + an offset applied in one place | Document broadcast desync as a platform-level concern for live content |

## Detail

---

### FL-01 — No way to tell which tool an utterance will route to

**Task** Confirm "what did I miss" routes to `what_did_i_miss` and not
`get_match_state`.

**Steps** Looked for a CLI or console preview. Searched the docs for
routing, arbitration, utterance testing. Found none.

**Expected** Something like `alexa-ai test-utterance "what did I miss"`
returning the chosen tool.

**Actual** The only way to find out is a round trip through a device.
Each iteration on a description is minutes, not seconds.

**Severity** important

**Workaround** `tests/test_routing_phrases.py`, which asserts that the
phrasings listeners use are present in the descriptions. It tests our
text, not the router — a proxy, not a check.

**Suggestion** Ship an utterance-to-tool preview in the Alexa AI CLI.
For a platform whose entire integration surface is tool descriptions,
this is the highest-value developer tool available and its absence is
felt within the first hour.

---

### FL-02 — Server cannot initiate a message

**Task** Tell a listener a goal has gone in, without them asking.

**Steps** Implemented the SSE channel on `GET /mcp` per the spec. Looked
for a documented path for an add-on to push to a device.

**Expected** Either a supported mechanism or an explicit statement that
there is not one.

**Actual** The transport supports server-initiated messages; the
platform does not surface them to the listener. We inferred this rather
than reading it.

**Severity** critical for our original design

**Workaround** Redesigned around on-demand questions. Arguably a better
product — see ACCESSIBILITY.md §8 — but it was a redesign, not a choice.

**Suggestion** State the constraint prominently in the MCP Toolkit
overview. One sentence saves a team a day. Longer term, a
"proactive notification" capability with user opt-in would open a whole
category: accessibility, safety, time-critical alerts.

---

### FL-03 — Writing tool descriptions is undocumented craft

**Task** Write eight descriptions that route reliably.

**Steps** Looked for guidance on length, example phrasings,
disambiguating adjacent tools, whether to write for a human or a model.

**Expected** A page of patterns and anti-patterns.

**Actual** Worked it out ourselves: lead with intent, embed real
phrasings, explicitly name the adjacent tool you are *not*.

**Severity** important

**Workaround** The three rules documented at the top of `registry.py`.

**Suggestion** Publish a "writing tool descriptions for Alexa+" page.
Include the adjacent-tool problem, which is non-obvious and bites
everyone with more than three tools.

---

### FL-04 — Bedrock default retry behaviour is wrong for voice

**Task** Keep catch-up under a 3 s ceiling.

**Steps** First implementation used default client config. Observed
occasional responses far past budget.

**Expected** Defaults tuned for interactive use, or a documented preset.

**Actual** Default retries can consume more wall-clock time than a voice
interaction has. A retried call is a wasted call — by the time it lands,
the template would have been better.

**Severity** important

**Workaround** `max_attempts=1`, 3 s read timeout, 1 s connect timeout,
and a template fallback on any failure.

**Suggestion** A documented low-latency interactive configuration, or a
note in the Bedrock docs for voice and real-time use cases.

---

### FL-05 — First Bedrock invoke after idle is slow

**Task** Keep the first catch-up of a match inside budget.

**Expected** Consistent latency.

**Actual** The first call after a quiet period is noticeably slower,
which on our budget is the difference between the model path and the
template path. For a match-day product the first call is the one a judge
or a listener notices.

**Severity** nice-to-have (we degrade cleanly)

**Workaround** Template fallback absorbs it. We considered a warm-up
ping on `follow_match` but did not want to pay for tokens nobody reads.

**Suggestion** Document the behaviour and a recommended warm-up pattern.

---

### FL-06 — MCP `_meta` has no shared conventions

**Task** Return a UI payload and per-tool timing without colliding with
anything.

**Actual** `_meta` is open. We invented `_meta.ui` and `_meta.sideline`.
Both work; neither is standard.

**Severity** nice-to-have

**Workaround** Namespacing by server name.

**Suggestion** Register conventional `_meta` keys in the spec, or
recommend reverse-DNS namespacing explicitly.

---

### FL-07 — Free football data tiers cannot support a live product

**Task** Poll a live match every 15 seconds.

**Steps** Evaluated free tiers before writing any server code.

**Expected** At least one tier capable of a single live match.

**Actual** Free tiers are either delayed — useless, the listener hears
the crowd before we know anything — or capped at roughly a hundred calls
a day against the ~360 a 90-minute match needs.

**Severity** important (not an Amazon issue; recorded because it shaped
the whole build)

**Workaround** Paid tier, plus the replay harness so development does
not depend on a live fixture.

**Suggestion** For hackathon organisers: a short list of data sources
with usable free tiers would materially change what gets built. Several
good ideas die on this and the organisers never hear why.

---

### FL-08 — GitHub collaborator invitations expire in seven days

**Task** Share a private repo with the reviewers.

**Actual** Documented, but the instinct is to add reviewers early, and
an invitation added three weeks before judging has lapsed by the time
anyone looks.

**Severity** nice-to-have, potentially critical if it silently costs a
submission

**Workaround** A line in SUBMISSION_CHECKLIST.md: send invitations at
submission time, not before.

**Suggestion** Surface the expiry in the submission form itself, next to
the repo URL field, where it will actually be read.

---

### FL-09 — Nothing warns you about broadcast desync

**Task** Answer "what's the score" without spoiling a goal the
listener's television had not shown yet.

**Steps** Compared data-feed arrival against stream timing. Searched the
Alexa+ and MCP docs for any guidance on live-content synchronisation.

**Expected** Some acknowledgement that a voice agent answering about
live content is ahead of the viewer, and a recommended pattern.

**Actual** Nothing. The failure is silent and it is the worst one this
product can commit: the companion becomes the thing that ruins the
match. A sighted friend in the room cannot spoil it, because they are
watching the same delayed picture. We can.

**Severity** important

**Workaround** `sync_broadcast_delay`. The listener reads their clock to
us once; we hold every answer back by the difference. Applied in
`resolve_fixture()` so no individual tool has to remember.

**Suggestion** Any platform guidance for live-content agents should name
this. It is not obvious until it happens, and by then it has happened to
a user.
