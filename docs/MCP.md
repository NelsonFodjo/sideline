# The MCP server: what it implements, and what it does not

Sideline is an MCP **server**. Alexa+ is the client; the web page in `simulator/` stands in for it ([simulator/README.md](../simulator/README.md)).
This page is the protocol surface in one place, so a reviewer does not have to read `sideline/mcp/server.py` to know
what is there. The tools themselves are in [TOOLS.md](TOOLS.md).

## Implemented

| Part | What it does | Pinned by |
|---|---|---|
| Transport | Streamable HTTP, spec revision 2025-11-25: `POST /mcp` (a request, a notification or a batch), `GET /mcp` (SSE stream), `DELETE /mcp` (end the session) | `tests/test_mcp_protocol.py` |
| Sessions | `Mcp-Session-Id` issued on `initialize`; an unknown one gets HTTP 404 so the client re-initialises; the listener's data is not in the session (it is keyed by listener id in the state store), so a dropped session loses nothing | same |
| Notifications | No `id` means HTTP 202 and no body | same |
| Version | `MCP-Protocol-Version` is sent on every response; a client asking for another revision is told what is spoken, never silently matched | same |
| `tools/list` | 27 tools, each with a description written for the model, a JSON Schema (`additionalProperties: false`), and **annotations**: `readOnlyHint`, `destructiveHint` (always false), `idempotentHint`, `openWorldHint`. Six tools change the listener's own state and say so: `follow_match`, `sync_broadcast_delay`, `set_favourites`, `set_preferences`, `what_did_i_miss`, `get_lineups` (the last two move the "told up to here" marker) | `tests/test_mcp_protocol.py`, `tests/test_routing_phrases.py` |
| Tools follow the feed | A tool is listed only if the feed can answer it (`registry.TOOL_REQUIRES`) | `tests/test_more_tools.py` |
| `tools/call` | Arguments are validated against the schema before the tool runs: a bad one is JSON-RPC `-32602`. Results carry `content` (the sentence to speak) and `structuredContent` (the detail, including `generated_by`: template, nova or tool) | same |
| Errors | Two kinds, on purpose: protocol errors (`-32602`, `-32601`, parse) and **tool errors** (`isError: true` with a sentence written to be spoken, plus `structuredContent.reason`). "I can't find that team" is not a transport failure | [TOOLS.md](TOOLS.md#errors) |
| Forks | When a request could mean several matches, the tool error lists up to four, numbered, with `detail.candidates`, and the client reads them out | [FINDER.md](FINDER.md) |
| MCP Apps | Screened devices get a card in `_meta.ui`; nothing essential is only in the card | [ACCESSIBILITY.md](ACCESSIBILITY.md) |
| Origin check | Every request's `Origin` is checked against `SIDELINE_ALLOWED_ORIGINS` (the DNS-rebinding guard the spec asks for); a request with no `Origin`, as Alexa+ sends, passes | `tests/test_mcp_protocol.py` |
| Own client | The voice agent calls the tools through this server's `/mcp`, as any client would, so the protocol is exercised by the product itself | `tests/test_mcp_client.py` |
| Audit | One JSON line per call (tool, arguments, time, outcome), `make log-report` | `tests/test_audit.py` |

## Not implemented, and why

| Not there | Why, and what that costs |
|---|---|
| **HTTPS and account linking** | The server is local HTTP. Alexa+ requires HTTPS, and account linking tooling is partner-only, so it could not be exercised. A real deployment needs a TLS front (a load balancer or API Gateway) and a link to the listener's Amazon account; until then the listener is one fixed id per server. See [HACKATHON.md](HACKATHON.md) and [FRICTION_LOG.md](FRICTION_LOG.md) (FL-02) |
| **Authorization (OAuth 2.1)** | Follows from the above. There is no token check on `/mcp`; the 401-without-`WWW-Authenticate` behaviour in the Alexa+ checklist is documented, not exercised end to end |
| **Tested against Alexa+ itself** | Not possible here. Tested against our own client and a simulated Alexa+. Routing quality is measured with Nova Micro (`make route-check`, 71 phrasings), which is **not** Alexa+'s own model, so how Alexa+ routes is unknown |
| **Tested against an independent MCP client** | Not done here (for example the MCP Inspector or another vendor's client). The server is written to the spec and the tests are ours; a second implementation could find something we agree with ourselves about |
| `outputSchema` | Results are described in prose (`_outputHint` is internal), not declared as a schema. `structuredContent` is stable in practice but not promised by the protocol |
| Resources and prompts | Only tools. Nothing here is naturally a resource, and a voice client has no use for a prompt template |
| Pagination, `listChanged`, cancellation, logging, completion, sampling | Not needed at 27 tools (`listChanged` is advertised as false); a call is one short request. The server does not push; Alexa+ cannot be spoken first, so nothing here promises "I'll tell you when" |
| Rate limiting | The football feed's own limit (180 calls an hour per kind of data) is the real ceiling and is handled; the server itself does not limit a client |
| Several listeners | One listener id per server. The state layer is keyed by listener, so the step is account linking, not a rewrite |

## Reading it quickly

```
curl -s localhost:8765/mcp -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

lists every tool with its annotations (no session needed for `tools/list`, which keeps `curl` and the MCP Inspector
usable). `make test` runs the protocol suite offline; `make route-check` runs the real model against the tool
descriptions.
