# Connecting to Alexa+

> **Read this first (official FAQ, read 2026-10-12).** The Alexa+ add-on
> tools this page describes (the `alexa-ai` CLI, the MCP Toolkit, the Web
> Simulator, account linking) are "in preview and available to select
> partners only - there is currently no way for hackathon participants to
> apply for or gain access". **You do not need them.** The rules and FAQ
> say to build a self-hosted MCP server and demo it through "your own
> web-based simulator", and that a web page acting as a real MCP client
> (initialize, tools/list, tools/call over Streamable HTTP) satisfies the
> track. That is what `simulator/index.html` is. Everything below is the
> **partner / future path**, kept because it is accurate and reusable, not
> because the submission depends on it.

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

Account linking is **optional** in Alexa+'s own docs: it is only for
tools that "genuinely require user identity". Sideline keeps one
catch-up window per listener, so it does.

Authentication is implemented in [sideline/auth.py](../sideline/auth.py)
and **off by default**, so the demo and the simulator work with no
identity provider. With `SIDELINE_AUTH=off` the listener is whatever the
`X-Sideline-Listener` header says, else one shared id: fine for a local
demo, **unsafe for more than one real listener**.

### What Alexa+ requires (from its docs, read 2026-10-12)

| Requirement | Who does it | Where |
|---|---|---|
| Unauthenticated request → `401`/`403` **without** a `WWW-Authenticate` header (the QuickStart lists that header as *not yet supported*) | this server | `auth.py`, tested in `test_auth.py` |
| `/.well-known/oauth-protected-resource` with `resource` (must exactly match the add-on manifest URL), `authorization_servers` (Alexa uses the first), `scopes_supported` | this server | `auth.py` |
| Bearer token in the `Authorization` header only | this server | `auth.py` |
| OAuth 2.1 authorization-code flow with PKCE **S256**, `resource` parameter | authorization server | your IdP |
| Refresh token returned with every access token | authorization server | your IdP |
| **Static** client registration (no DCR); register every redirect URI Alexa lists | authorization server | your IdP |
| `/.well-known/oauth-authorization-server` advertising `code_challenge_methods_supported` with `S256`. **Deployment is blocked without it** | authorization server | your IdP |
| A public privacy policy and terms URL | you | `addon.json` |

Turn it on with:

```bash
SIDELINE_AUTH=required
SIDELINE_AUTH_ISSUER=https://<your authorization server>
SIDELINE_PUBLIC_URL=https://<your-host>/mcp         # == the add-on manifest URL
SIDELINE_AUTH_JWKS_URL=https://<your authorization server>/<jwks path>
SIDELINE_AUTH_SCOPES="sideline.read"
```

The server checks signature (RS256 from the JWKS, or HS256 for testing),
expiry, issuer, and the token's `sub`, which becomes the listener id.
`aud` is enforced only if you set `SIDELINE_AUTH_AUDIENCE`, because
Alexa's docs do not say tokens carry one. `make test` exercises all of
this with real signatures.

### The part that is genuinely open

This server is only the *resource* server. The authorization server must
publish `/.well-known/oauth-authorization-server`. **I have not verified
that Amazon Cognito does**: as I understand it Cognito publishes
`/.well-known/openid-configuration` instead, which would block deployment.
Check your IdP's discovery document against the table above before
building on it. Nothing here has been tested against a real Alexa+
account link.

If this is too heavy for the time left, the rules allow a **simulated
Alexa+ experience** instead of a deployed add-on (see
[OFFICIAL_RULES.md](OFFICIAL_RULES.md)), and the demo and the repo are
what judges mostly see.

## Verifying before you connect

```bash
make test        # protocol conformance, no network
python3 scripts/smoke_test.py
```

If `test_mcp_protocol.py` passes, the transport is conforming. Connect
the add-on after that, not before — debugging a protocol bug through a
device is miserable.
