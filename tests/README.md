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
