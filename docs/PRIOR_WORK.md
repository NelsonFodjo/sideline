# Prior work

> If your project existed before the hackathon, a clear explanation of
> what you built or changed during the submission window.

**What the repository itself shows:** its first commit is dated
2026-10-12, after the submission window opened on 2026-08-31
(`git log --reverse`). Nothing in the history predates the window.

**What only you can confirm before submitting:** that no code in this
repository was brought in from earlier work. If any was, the rules require
you to explain what was significantly updated during the window and to
show it in the demo. This page is a statement of the git history, not a
substitute for your own declaration.

**Third-party material used:**

| What | How it is used | Terms |
|---|---|---|
| StatsBomb Open Data | the bundled real match, built with `scripts/build_statsbomb_replay.py` | attribution **and their logo** requested on publication; we attribute in text and omit the logo (DATA_PROVIDERS.md) |
| API-Football | optional live provider; never run with a real key | you must be authorised under their terms (rules, "Third Party Integrations"); their terms were not retrievable here |
| MCP specification 2025-11-25 | implemented from the spec, no SDK | open standard |
| boto3 | optional; Bedrock, DynamoDB, Polly, Secrets Manager | AWS SDK |
| cryptography | optional; RS256 token verification | library licence |
| Public Sans, IBM Plex Mono | simulator fonts (loaded from Google Fonts) | open licences; confirm before relying on this |
| Python standard library | everything else | n/a |

Nothing else is vendored or copied.
