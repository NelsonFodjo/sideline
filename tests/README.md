# Tests

```bash
make test
```

No network. No credentials. No fixtures that flatter us.

| Suite | What it protects |
|---|---|
| `test_clean_clone.py` | The repo works the way the README says. Added after `python3 -m sideline` — the first line of the README — failed on a fresh clone because every test ran with `PYTHONPATH` set. |
| `test_routing_phrases.py` | Tool descriptions still contain the phrasings listeners use. Descriptions are the routing surface; this breaks silently when someone tidies the wording. |
| `test_language.py` | Phrasing, goal-before-card ordering, stoppage time, and the invented-scoreline guard. |
| `test_tools.py` | All nine tools, plus every failure a listener can reach. |
| `test_what_did_i_miss.py` | The gap logic. **If this breaks, the submission is not worth filming.** |
| `test_summaries.py` | Non-strict cached catch-ups and strict live mode: precompute/cache behavior, template-on-miss outside live mode, grounding, translation and live cache bypass. Uses a simulated slow model, never Bedrock. |
| `test_envfile.py` | `.env` loading: environment variable > file > default; blank values skipped; the shipped `.env.example` has no commented-out settings. |
| `test_autodetect.py` | Bedrock, live data and DynamoDB switch on when their credentials are present, explicit values win, and an unreachable table falls back to memory. |
| `test_auth.py` | Bearer-token verification: real RS256 and HS256 signatures, expiry, issuer, audience, `alg=none`, 401 + `WWW-Authenticate`, RFC 9728 metadata, and that the listener id is the token's `sub`. |
| `test_statsbomb.py` | Regressions found replaying a real match: second yellow is a red, a Bad Behaviour booking is kept, the line-up reads goalkeeper first. |
| `test_apifootball.py` | The live provider against canned API-Football responses: missed penalty is not a goal, second yellow is a red, a bad key or exhausted quota is an error not "no match", pre-kick-off fixtures are found. |
| `test_aws_helpers.py` | Secrets Manager key retrieval and the CloudWatch EMF metric line, with fakes: no AWS account. |
| `test_mcp_protocol.py` | Conformance against spec 2025-11-25: sessions, 202 on notifications, batches, schema rejection, DELETE. |

## The ones that matter most

**`test_what_did_i_miss.py`** asserts the behaviours the product is:

- answering a question moves the marker
- the marker stays frozen while nobody asks
- the catch-up covers exactly the listener's gap
- asking twice does not repeat
- the marker never goes backwards
- **asking the score does not swallow the goal** — the easiest thing to
  break later while "optimising"

**`test_mcp_protocol.py`** stops us shipping something that works in our
own simulator and fails the moment a real MCP client connects.
