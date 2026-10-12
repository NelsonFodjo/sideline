# Scoring this against the rubric

Honest self-assessment, criterion by criterion. Written so the team knows
where we are strong, where we are thin, and what to fix first.

---

## 1. Tech Implementation

> *How well is the project built, and how effectively does it use the
> required APIs, SDKs or device capabilities?*

**Where we win**

- A real MCP server, written to spec 2025-11-25 over Streamable HTTP,
  with no SDK. Sessions, notification semantics, batches, Origin
  validation, protocol version echo — and `tests/test_mcp_protocol.py`
  proves each one. The submission rules demand the repo *actually call
  the technology in code*; this is about as unambiguous as that gets.
- The background poller. Most entries will be request/response only. A
  scheduled job that runs with nobody in the room is the structural
  difference between a lookup and a product.
- Durable, deduplicated event state with a non-trivial access pattern,
  and the gap calculation on the shared base class so backends cannot
  drift.
- Eight small, resumable tools rather than one fat one — which is also
  what makes interruption survivable.
- Zero runtime dependencies. A judge can clone and run it.

**Where we are thin**

- **Bedrock is commented out.** Defensible, and documented as a
  packaging decision, but a judge wanting to see a model in the loop
  sees commented code. *Fix: turn it on for the demo and film one
  catch-up with `generated_by: "bedrock"` visible in the response.*
- **DynamoDB is reference-only.** Same argument, same risk.
- The in-memory store is not multi-process safe. Fine for a demo,
  stated in the docs, but it is a real limit.

---

## 2. Design

> *Does it deliver a complete, coherent product experience? Is the
> interaction model intuitive and well-considered for the target device?*

**Where we win — this is our strongest criterion**

- Voice is not an adaptation here. It is the only channel the user has.
  Nothing else in the track will be able to say that honestly.
- The interaction model is copied from how blind fans actually watch:
  one question at a time, to someone sitting beside them, interruptible.
  It was not designed around the platform and then rationalised.
- `ACCESSIBILITY.md` turns that into eight testable rules — nothing
  essential on screen only, lead with the fact, goals before
  chronology, never repeat, refusals are spoken.
- Every error a listener can reach is a sentence a person would say.
- The MCP Apps cards enhance for a sighted person in the room and never
  substitute.

**Where we are thin**

- **No blind user has used it.** This is the single biggest hole in the
  submission, and it is in Design as much as Impact. *Fix: one person,
  one match, one afternoon.*

---

## 3. Potential Impact

> *A credible, specific case for solving customer needs. Could it serve
> an audience beyond the hackathon?*

**Where we win**

- The problem is specific and checkable: line-ups shown once as a
  graphic, the referee named once, substitutions on a board, the clock
  permanently on screen. Not "accessibility is important."
- Beyond-the-hackathon is answered by an artefact, not a claim: the
  sports-feed-to-MCP adapter is useful to anyone, and the server is MIT.
- It generalises. Nothing in the architecture is football-specific below
  the provider layer.

**Where we are thin**

- **Argument, not evidence.** Ten seconds of a real person completing a
  task they could not do before converts this from a 7 to a 9. Nothing
  else we can do in the time moves a score this much.
- No figures on audience size. We deliberately did not invent any.
- Live data costs money, which is a real adoption barrier and we say so.

---

## 4. Quality of the Idea

> *Creative, imaginative use of the tools, with genuine understanding of
> the developer ecosystem and end-user needs.*

**Where we win**

- Nobody else will think of the referee, the bench, or the catch-up
  window. The idea is specific rather than a category.
- The ecosystem half is evidenced rather than asserted: an open-source
  adapter, eight friction-log entries with severities and suggestions,
  and documented reasoning about tool descriptions as a routing surface
  — which is a platform insight, not an implementation note.
- We state platform limits plainly instead of hiding them. The SSE
  channel is implemented and held open for a capability that does not
  exist yet.

**Where we are thin**

- Sport may read as light next to a health or safety entry. *Mitigation:
  lead the video with the person, not the scoreboard. The first twenty
  seconds decide which of the two they think they are watching.*

---

## The bonus

> *Submissions with friction logs can earn up to a 10% judging bonus.*

Eight entries, each with task, steps, expected vs actual, severity,
workaround and an actionable suggestion. Written as we hit them.

Most entrants will submit two lines on the last night. This is the
cheapest grade available and we have taken it.

---

## If we fix only three things

**1. Film a blind person using it.** Moves Impact and Design together.
Nothing else comes close.

**2. Turn Bedrock on and film one catch-up with `generated_by:
"bedrock"` in the response.** Closes the only real hole in Tech
Implementation, and it is an afternoon.

**3. Record a genuine match with `scripts/record_match.py` and replace
the placeholder replay file.** Removes the one thing in the repo that
could read as fabricated.

## What we must not do

- Put a club badge, league logo or broadcast clip in the video. The
  rules forbid third-party trademarks and it is an avoidable
  disqualification.
- Imply replayed data is live. Say "a recorded match, replayed."
- Send the GitHub reviewer invitations early. Seven-day expiry.
