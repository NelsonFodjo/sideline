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
| `test_mcp_client.py` | The voice agent's tool calls really cross `/mcp`: a session, `tools/call`, declined tools as errors with detail, server-side argument validation, the listener header, the agent-facts flag, re-initialising a lost session. |
| `test_routing_phrases.py` | Tool descriptions still contain the phrasings listeners use. Descriptions are the routing surface; this breaks silently when someone tidies the wording. |
| `test_tools.py` | All nine tools, plus every failure a listener can reach. |
| `test_what_did_i_miss.py` | The gap logic. **If this breaks, the product is not worth filming.** |
| `test_language.py` | Phrasing, goals before cards, stoppage time, and the rule for Bedrock: on means a wrong score, an empty answer or an error is reported (and the listener's gap is kept); off means the template. Also a catch-up never loses headlines it did not read out. |
| `test_agent.py` | Nova receives the MCP schemas and calls registered tools; thinking tags are stripped; no canned fallback. |
| `test_apifootball.py` | The live provider against canned API-Football responses: a missed penalty is not a goal, a second yellow is a red, "Normal Goal" is not read aloud, head-to-head sends no `last` and excludes the live match, a bad key or exhausted quota is an error and not "no match". |
| `test_dynamo.py` | The DynamoDB store against a fake table that rejects floats and honours the conditional write. Pins the two bugs the first real-table run found. |
| `test_broadcast_sync.py` | The spoiler guard: the listener's picture runs behind the feed, so we hold back; it fails safe. |
| `test_pronouns.py` | "Who is he?" resolves from what just happened, and refuses rather than guesses. |
| `test_clock.py` | The current time and a fixture's kickoff: parsing (a trailing Z, offsets, garbage), durations said as people say them, the "Kick-off is in 2 hours 15 minutes" sentence and its past/unknown forms, and that `follow_match` and `get_match_state` use it. Time is pinned, never the real clock. |
| `test_sports.py` | The sport seam: the whole stack on basketball (an invented game) beside football; scoring by points; a replay review superseding a basket. |
| `test_resolve.py` | Understanding what was meant: mispronounced answers snap to the option offered (14 cases), ordinals, refusing ties and non-matches, expiry, name repair without touching ordinary words, and the real two-Arsenal ambiguity end to end. |
| `test_voice.py` | Speech in: the provider order (Groq with a key, Nova Sonic, then the browser) and per-clip fallback, silence not retried, a named provider used alone, the Groq request shape, the vocabulary hint, and the keyboard gate (typing is dropped before any request; speech over typing is kept). No real recognition: that is `make stt-check` and `make compare-stt`. |
| `test_simulator.py` | The page is served same-origin and speaks MCP; the speech detector under Node (typing, fast typing, a thump, speech over typing, a learned hum). |

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
