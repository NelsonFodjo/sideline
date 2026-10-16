# Security policy

## Reporting a vulnerability

Please do not open a public issue. Report it privately through
[GitHub's private vulnerability reporting](https://github.com/NelsonFodjo/sideline/security/advisories/new). You will get
an acknowledgement, and a fix or a decision, as soon as the maintainer can; this is a small project with one maintainer, so
no response time is promised.

## What is in scope

- The MCP server in `sideline/`: the `/mcp` endpoint, origin checks, the optional bearer token (`SIDELINE_AUTH_TOKEN`),
  listener state, and anything that could make the server read or write outside what it is asked.
- The simulator routes it adds (`/agent/chat`, `/voice/stt`, `/voice/tts`), which can spend the operator's AWS credits.

## What you should know before deploying

- **There is no OAuth.** The bearer token keeps a deployment from being open; it is not account linking. See
  [README, "Connect it to anything"](README.md#connect-it-to-anything-and-host-it-later).
- **One listener per deployment.** State is keyed by the `X-Sideline-Listener` header; do not give one server to several
  real people.
- **The simulator is for local use.** It does not send the token, and its voice routes call AWS on the operator's account.
- **Never commit `.env`.** It is in `.gitignore`; `make env` shows what is set without printing a secret.

## Supported versions

Only the latest release and `main` get fixes.
