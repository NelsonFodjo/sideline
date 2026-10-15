# The MCP server: what it implements, and what it does not

Sideline is an MCP **server**. Alexa+ or another MCP-capable host is the client; the web page in `simulator/` stands in for it ([simulator/README.md](../simulator/README.md)).
This page is the protocol surface in one place, so a reviewer does not have to read `sideline/mcp/server.py` to know
what is there. The tools themselves are in [TOOLS.md](TOOLS.md).

## Implemented

| Part | What it does | Pinned by |
|---|---|---|
| Transport | Streamable HTTP, spec revision 2025-11-25: `POST /mcp` (a request or a notification; a JSON-RPC batch is refused with 400, as the spec has dropped them), `GET /mcp` (SSE stream), `DELETE /mcp` (end the session) | `tests/test_mcp_protocol.py` |
| Sessions | `Mcp-Session-Id` is issued on a successful `initialize` and required after it (400 without, 404 if unknown so the client re-initialises); the listener's data is not in the session (it is keyed by listener id in the state store), so a dropped session loses nothing. `MCP-Protocol-Version`, when sent, must be 2025-11-25 | `tests/test_mcp_protocol.py`, `tests/test_fix_server.py` |
| Notifications | No `id` means HTTP 202 and no body | same |
| Version | `MCP-Protocol-Version` is sent on every response; a client asking for another revision is told what is spoken, never silently matched | same |
| `tools/list` | 30 tools, each with a description written for the model, a JSON Schema (`additionalProperties: false`), and **annotations**: `readOnlyHint`, `destructiveHint` (always false), `idempotentHint`, `openWorldHint`. Six tools change the listener's own state and say so: `follow_match`, `sync_broadcast_delay`, `set_favourites`, `set_preferences`, `what_did_i_miss`, `get_lineups` (the last two move the "told up to here" marker) | `tests/test_mcp_protocol.py`, `tests/test_routing_phrases.py` |
| Tools follow the feed | A tool is listed only if the feed can answer it (`registry.TOOL_REQUIRES`) | `tests/test_more_tools.py` |
| `tools/call` | Arguments are validated against the schema before the tool runs: a bad one comes back as a tool error (`isError: true`, `reason: "invalid_arguments"`) the model can correct. Results carry `content` (the sentence to speak) and `structuredContent` (the detail, including `generated_by`: template, nova or tool) | same |
| Errors | Two kinds, on purpose: protocol errors (`-32602` for malformed params or an unknown tool, `-32601`, parse) and **tool errors** (`isError: true` with a sentence written to be spoken, plus `structuredContent.reason`). "I can't find that team" is not a transport failure | [TOOLS.md](TOOLS.md#errors) |
| Forks | When a request could mean several matches, the tool error lists up to four, numbered, with `detail.candidates`, and the client reads them out | [FINDER.md](FINDER.md) |
| Card data | Screened devices can draw `_meta.sideline.ui`; nothing essential is only in the card. This is not the MCP Apps extension: the server declares no such capability and serves no `ui://` resource | [ACCESSIBILITY.md](ACCESSIBILITY.md) |
| Origin check | Every request's `Origin` is compared as scheme, host and port against `SIDELINE_ALLOWED_ORIGINS` (the DNS-rebinding guard the spec asks for); a request with no `Origin`, as Alexa+ sends, passes. A rejected request closes its connection, so a request smuggled in its body cannot run | `tests/test_mcp_protocol.py`, `tests/test_fix_server.py` |
| Own client | Before a turn, the simulator's Nova host fetches `initialize` instructions and `tools/list` through `/mcp`; Nova receives the live definitions, and selected tools are called back through `/mcp` | `tests/test_mcp_client.py` |
| Audit | One JSON line per call (tool, arguments, time, outcome), `make log-report` | `tests/test_audit.py` |

## Not implemented, and why

| Not there | Why, and what that costs |
|---|---|
| **HTTPS and account linking** | The server is local HTTP. Alexa+ requires HTTPS, and account linking tooling is partner-only, so it could not be exercised. A real deployment needs a TLS front (a load balancer or API Gateway) and a link to the listener's Amazon account; until then the listener is one fixed id per server. See [HACKATHON.md](HACKATHON.md) and [FRICTION_LOG.md](FRICTION_LOG.md) (FL-02) |
| **Authorization (OAuth 2.1)** | Follows from the above. Only a static bearer token is supported: with `SIDELINE_AUTH_TOKEN` set, every route but `/health` answers 401 with `WWW-Authenticate: Bearer` unless `Authorization: Bearer <token>` is sent (tested). That is not OAuth: no discovery document, no token issuing, no scopes. It keeps a deployment from being open; it does not link a listener to an Amazon account |
| **Tested against Alexa+ itself** | Not possible here. Tested against our own client and a simulated Alexa+. Routing quality is measured with Nova Micro (`make route-check`, 71 phrasings), which is **not** Alexa+'s own model, so how Alexa+ routes is unknown |
| **Tested against more than one independent MCP client** | One was run: the official MCP Python SDK 2.3.0 (`scripts/check_with_sdk.py`: initialize, `tools/list`, two live tool calls, one bad argument returned as a tool error). The MCP Inspector and other vendors' clients were not |
| `outputSchema` | Results are described in prose (`_outputHint` is internal), not declared as a schema. `structuredContent` is stable in practice but not promised by the protocol |
| Resources and prompts | Only tools. Nothing here is naturally a resource, and a voice client has no use for a prompt template |
| Pagination, `listChanged`, cancellation, logging, completion, sampling | Not needed at 30 tools (`listChanged` is advertised as false); a call is one short request. The server does not push; Alexa+ cannot be spoken first, so nothing here promises "I'll tell you when" |
| Rate limiting | ESPN publishes no limit for these endpoints. The provider caches by kind of data and shares one request between simultaneous askers, so a busy day stays light on the feed; the server itself does not limit a client |
| Several listeners | One listener id per server. The state layer is keyed by listener, so the step is account linking, not a rewrite |

## Reading it quickly

The handshake a client performs (`initialize`, then the `Mcp-Session-Id` it is given on every later request, then
`tools/list`) is written out as `curl` commands in the README's "Connect it to anything" section. A session is required
after `initialize`; `GET /health` needs none. `make test` runs the protocol suite offline; `make route-check` runs a
real model against the tool descriptions.

Bedrock Nova does not connect to MCP by itself. A host must discover the MCP tools, pass their descriptions
and schemas to Nova, then execute Nova's tool requests. Sideline's simulator gives Nova the current full
catalog up front, preserving each tool's examples and distinctions. Nova can request multiple tools in one
response; the host only dispatches names present in the discovered catalog and returns results together for
Nova to compose. A separate
MCP host can connect directly to the same `/mcp` endpoint.
