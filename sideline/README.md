# sideline: the MCP server

This folder is the product: a live-sports MCP server (spec 2025-11-25, Streamable HTTP, 30 tools). Take this folder and
you have the MCP. Nothing outside it is needed to run it.

- **Needs:** Python 3.8+. The standard library is enough. `boto3` is optional (Bedrock wording, DynamoDB state); without
  it the server answers in templated wording and keeps state in memory.
- **Data:** ESPN's public endpoints, no key.
- **Run:** from the folder that contains `sideline/`: `python3 -m sideline` (listens on `127.0.0.1:8765`, endpoint `/mcp`,
  health at `/health`). Settings come from the environment or a `.env` next to the folder; the full list is in
  `config.py` (`VARIABLES`).
- **Protect it before hosting it:** set `SIDELINE_AUTH_TOKEN`; see "Connect it to anything, and host it later" in the
  top-level README.

| Part | What it is |
|---|---|
| `mcp/` | the protocol: server, tool registry, schema validation, errors |
| `tools/` | the 30 tools, one file each |
| `providers/` | where the data comes from (ESPN) |
| `state/` | what each listener has heard (memory or DynamoDB) and the spoiler guard |
| `sports/` | per-sport wording (football, basketball, American football, baseball, hockey) |
| `finder.py`, `resolve.py`, `names.py` | working out which match, team or player a question means |
| `poller.py`, `cache.py`, `clock.py` | live reading, caching, the listener's delay |
| `language/` | optional model-written wording (Bedrock) and the fallback templates |

Alongside this folder in the repository, and not part of the MCP: `simulator/` (a web page that plays the part of Alexa+
so the MCP can be tried by voice), `tests/`, `scripts/` (benchmarks and checks for developers) and `docs/`. If
`simulator/` is present the server also serves it; if not, the MCP is unchanged.
