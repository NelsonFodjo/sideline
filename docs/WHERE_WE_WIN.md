# Self-assessment against the rubric

**This is an opinion, not evidence.** It is the authors' reading of the
official criteria, written to decide what to fix first. Facts it relies on
are in [EVIDENCE.md](EVIDENCE.md); where a point has no evidence it says so.
No claim is made about other entries.

The criteria, from the official rules (read 2026-10-12, see
[OFFICIAL_RULES.md](OFFICIAL_RULES.md)): four, **equally weighted**, after a
pass/fail Stage One; plus up to +10% for friction logs.

## Tech Implementation

*How well is it built, and how effectively does it use the required tech?*

**Backed by evidence**
- A self-hosted MCP server on Streamable HTTP, spec 2025-11-25, from the
  standard library, with a conformance suite that passes (`make test`,
  16 suites).
- Server-side response time is well under the 500 ms Alexa+ target for
  every tool measured (EVIDENCE.md), with templates.
- A background poller, deduplicated event log and the gap calculation on a
  shared base class.

**Gaps, stated plainly**
- Nova Bedrock invocation, agent tool use and live catch-up were verified
  once; DynamoDB, end-to-end Polly/Transcribe audio, the live feed and the
  CloudFormation deployment have not been exercised against real services.
- The Bedrock catch-up's latency is unmeasured and may exceed 500 ms.
- The CloudFormation stack has never been deployed.

## Design

*A complete, coherent experience; an interaction model suited to the platform.*

**Backed by evidence**
- Voice-only by design: every fact is in the spoken text, every failure a
  sentence (`tests/test_tools.py`), nothing requires sight to arm
  (`tests/test_broadcast_sync.py`).
- The simulator is a real MCP client and is served by the server
  (`tests/test_simulator.py`).

**Gaps**
- No blind or low-vision person has used it.
- Whether a card (MCP Apps UI payload) renders in any Alexa+ client is
  unverifiable: no participant can reach one.

## Potential Impact

*A credible, specific case; could it serve an audience beyond the hackathon?*

**Backed by evidence**
- The need is specific and checkable against how a broadcast works
  (line-ups shown once, score on screen), but that is reasoning, not
  measured evidence.
- The provider interface isolates the data source, so another feed can be
  swapped in; the bundled replay shows it working on real events.

**Gaps**
- No user evidence. No audience-size figure (none is invented here).
- Live data has a cost, which is a real barrier.

## Quality of the Idea

*Creative use of the tools; genuine understanding of the ecosystem and user.*

**Against the rules' own examples for Alexa+:** "basic MCP wrapper around an
existing API" is called obvious; "a context-aware add-on that maintains
state across sessions" is called creative. The per-listener `last_told_at`
state is this project's answer, and a live feed alone would not be.

**Gaps**
- The Bedrock use is closer to the rules' "single Bedrock call" than to a
  multi-service pipeline.

## Friction-log bonus

Eight entries, each tied to a cited source (FRICTION_LOG.md). The bonus is
assessed by Amazon's team; whether these earn any of it is theirs to judge.

## What to fix first, in order

1. **Verify the remaining integrations.** Run `make create-table` and
   `make verify-data`, then exercise the simulator audio paths; preserve
   the outputs separately from the dated evidence snapshot.
2. **A real user session**, if one can be arranged, filmed with consent.
3. **Measure precomputed summaries against real Bedrock**: the cache
   mechanism is tested with a simulated model; strict live mode bypasses
   it and invokes Nova per request (BEDROCK.md).
4. **Fill every `TODO(you)`** in PRODUCT_FEEDBACK.md from real runs.

## What not to do

- Put a club badge, league logo or broadcast clip in the video.
- Imply replayed data is live.
- Claim only integrations that have actually been verified; EVIDENCE.md
  is a dated snapshot, with later AWS verification noted in AWS_SETUP.md.
- Send private-repo invitations early (7-day expiry); a public repo avoids it.
