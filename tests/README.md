# Tests

```bash
make test
```

No network, no credentials, no install: the suites run offline and deterministically, and secrets are blanked so a
developer's own keys can never reach a test. (Node, if present, also runs the browser-side speech detector.)

The match data in the tests is **not real**. `tests/support.py` is a test double for the live feed that plays back
the small, **invented** fixtures in `tests/fixtures/` (made-up teams, players and events, labelled as such) on a
clock the test controls. The product ships no recorded or demo data; `test_clean_clone.py` enforces that.

| Suite | What it protects |
|---|---|
| `test_clean_clone.py` | The repository works the way the README says: `python -m sideline` refuses clearly with no football key and serves with one; nothing that was removed has come back; no data files in the product; no virtualenv tracked in git. |
| `test_environment.py` | No dead settings and no undocumented ones: the code, `config.VARIABLES`, `.env.example` and `docs/ENVIRONMENT.md` name exactly the same variables, and every secret is blank in the example. |
| `test_envfile.py` | `.env` loading: environment variable over file over default; blank values skipped. |
| `test_mcp_protocol.py` | Conformance against spec 2025-11-25: sessions, 202 on notifications, batches, schema rejection, DELETE. |
| `test_mcp_client.py` | Nova's host discovers `tools/list` over `/mcp`, then calls tools over the same protocol: declined tools as errors with detail, server-side argument validation, the listener header, the model-facts flag, re-initialising a lost session. |
| `test_routing_phrases.py` | Tool descriptions still contain the phrasings listeners use. Descriptions are the routing surface; this breaks silently when someone tidies the wording. |
| `test_tools.py` | The core eleven tools, plus every failure a listener can reach. |
| `test_what_did_i_miss.py` | The gap logic. **If this breaks, the product is not worth filming.** |
| `test_language.py` | Phrasing, goals before cards, stoppage time, and the rule for Bedrock: on means a wrong score, an empty answer or an error is reported (and the listener's gap is kept); off means the template. Also a catch-up never loses headlines it did not read out. |
| `test_agent.py` | Nova receives the full MCP catalog and schemas up front, can request multiple tools in one response, and receives their results together; thinking tags are stripped; no canned fallback. |
| `test_sportmonks.py` | The live feed provider, against **invented** responses in Sportmonks' shape (checked against a real match too: see the README): states to our short codes, only the current score, a missed penalty is not a goal, a second yellow is a red, substitutions on/off, line-ups with formations, the token in a header and never a URL, 429/401/403 carrying the vendor's own words. It does not prove the live service agrees: that is `make verify-data` with a token. |
| `test_dynamo.py` | The DynamoDB store against a fake table that rejects floats and honours the conditional write. Pins the two bugs the first real-table run found, and that only matches with a current follower are polled. |
| `test_focus.py` | The conversation's topic: the match, team and player just discussed reach the next turn, a pronoun never becomes the topic, a new match drops the old player, and it expires. |
| `test_finder.py` | Which match is meant: a played match reported in full with nothing followed, parts by name, `last`/`next`/a date, a numbered fork with scores and days and the pick answering the original question, a follow-up using the last match asked about, a stale followed match forgotten, no spoiler delay on a played match, squad/stats/form/schedule with no match, and a server built on test data never touching a real table. |
| `test_poller.py` | The poller spends the feed's hourly limit: a match in play is read every cycle, one not yet started every few minutes (every cycle from ten minutes before kick-off), a finished one once and then left alone. |
| `test_audit.py` | The logs folder: a file per day, a JSON line per call, secrets replaced with `***`, old files pruned, and off means off. |
| `test_broadcast_sync.py` | The spoiler guard: the listener's picture runs behind the feed, so we hold back; it fails safe. |
| `test_pronouns.py` | "Who is he?" resolves from what just happened, and refuses rather than guesses. |
| `test_more_tools.py` | The other sixteen tools: search, competitions, tables (said as first, second...), top scorers, schedule, match stats, a player's season, injuries, form, favourites, preferences, capabilities. A missing thing is said, never guessed; favourites are only what the listener gave; tools are listed only where the feed can answer. |
| `test_fixtures.py` | What is on: every match named with its time (a list, "which one?", "did you mean?"), live first then the big competitions, five read and the rest counted, by competition, live only and tomorrow. |
| `test_preview.py` | The match preview: ground, time in the listener's zone (UTC when unknown), weather, formations and the estimate, each real or left out and listed; no id is ever spoken; the weather is placed only when the country matches. |
| `test_clock.py` | The current time and a fixture's kickoff: parsing (a trailing Z, offsets, garbage), durations said as people say them, the "Kick-off is in 2 hours 15 minutes" sentence and its past/unknown forms, and that `follow_match` and `get_match_state` use it. Time is pinned, never the real clock. |
| `test_sports.py` | The sport seam: the whole stack on basketball (an invented game) beside football; scoring by points; a replay review superseding a basket. |
| `test_resolve.py` | Understanding what was meant: mispronounced answers snap to the option offered (14 cases), ordinals, refusing ties and non-matches, expiry, name repair without touching ordinary words, and the real two-Arsenal ambiguity end to end. |
| `test_voice.py` | Speech in: the model order (Voxtral, Nova Sonic, then the browser) and per-clip fallback, silence not retried, a named model used alone, the Voxtral request shape (audio first, no system message) and its guard against answering, the vocabulary hint, and the keyboard gate (typing is dropped before any request; speech over typing is kept). No real recognition: that is `make stt-check` and `make compare-stt`. |
| `test_simulator.py` | The page is served same-origin and speaks MCP; the speech endpoints refuse foreign origins and oversized clips; the speech detector under Node (typing, fast typing, a thump, speech over typing, a learned hum). |

## The ones that matter most

**`test_what_did_i_miss.py`** asserts the behaviours the product is:

- answering a question moves the marker
- the marker stays frozen while nobody asks
- the catch-up covers exactly the listener's own gap
- a long absence gives headlines and an offer, and "the rest" still returns what was skipped
- nothing is ever repeated, and nothing is ever skipped

**`test_resolve.py`** pins the rule that keeps a blind listener safe: when two options fit about equally, ask
again, never guess.

## What these do not prove

They run against invented data and fakes. What was actually run against a real feed and a real AWS account is in
the README's verification table, with the commands to repeat it (`make verify-data`, `make aws-check`,
`make stt-check`, `make compare-stt`).
