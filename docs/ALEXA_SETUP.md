# Connecting to Alexa+

## What you need first

- An MCP server reachable at a remote HTTPS URL. Locally, a tunnel.
- The Alexa AI CLI.
- A developer account with access to the MCP Toolkit.

Note the toolkit's documented regional availability before planning
around it. See FL-02 and the product feedback.

## Path A — the add-on Agent Skill (recommended)

The Add-on Agent Skill walks a coding agent through onboarding. It works
in Claude Code, Kiro, Cursor, VS Code Copilot, or anything with shell
access.

```
I have an MCP server at https://<tunnel>/mcp for a live football
accessibility service. Help me create an Alexa+ MCP add-on.
```

It will:

1. **Introspect** — connect over Streamable HTTP, list our tools,
   propose an add-on name. You confirm.
2. **Scaffold** — `alexa-ai new mcp`, filling short and full
   descriptions and example phrases derived from the tools.
3. **Collect compliance assets** — privacy policy URL, terms URL, icons,
   carousel image.
4. **Validate and deploy**.

## Path B — the CLI directly

```bash
alexa-ai configure

alexa-ai new mcp \
  --name "Sideline" \
  --locale en-US \
  --mcp-server-url "https://<your-host>/mcp"

alexa-ai deploy
```

Re-run `alexa-ai deploy` whenever tools or descriptions change. The
add-on caches the tool list; a changed description does nothing until
you redeploy. That is a surprisingly easy half-hour to lose.

## Example phrases

These go in the add-on listing and should mirror the phrasings in the
tool descriptions:

```
"follow the Arsenal game"
"what did I miss"
"who's playing today"
"who's refereeing"
"what's the score"
```

## Account linking

Our listener state is keyed on the account-linked subject. Without
linking, every listener shares one id and one catch-up window — fine for
a local demo, wrong for anything real.

> **Status: not implemented in this repository.** The server does not
> verify tokens, return 401, or serve RFC 9728 metadata. It identifies a
> listener by an `X-Sideline-Listener` header, falling back to one shared
> id. That is acceptable for the local demo and the simulator and
> **unsafe for more than one real listener**. The verification block in
> `app.resolve_listener()` is a commented sketch, not working code.

Requirements for a real deployment: OAuth 2.1 with PKCE, 401 responses without a
`WWW-Authenticate` header, RFC 9728 protected resource metadata, and the
`resource` parameter set to the server's canonical URI.

`app.resolve_listener()` is the single place the identity is read. The
JWT verification block is written out and commented there — one function,
deliberately, because getting it wrong means one listener hears another
listener's catch-up.

## Verifying before you connect

```bash
make test        # protocol conformance, no network
python3 scripts/smoke_test.py
```

If `test_mcp_protocol.py` passes, the transport is conforming. Connect
the add-on after that, not before — debugging a protocol bug through a
device is miserable.
