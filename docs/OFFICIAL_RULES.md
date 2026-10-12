# The official rules, as read on 2026-10-12

Read directly from the Devpost rules page and Amazon's Alexa+ developer
docs, not from summaries. Where a source did not say something, this page
says so rather than guessing. Re-read the sources before submitting;
rules can change ("subject to change at any time", rules §11).

Sources:
[Devpost rules](https://amazonappdev2026.devpost.com/rules) ·
[Devpost overview](https://amazonappdev2026.devpost.com/) ·
[Alexa+ MCP QuickStart](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html) ·
[Account Linking for MCP Add-ons](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-account-linking.html) ·
[Design Guide: Tools, Schema, and Data Design](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-addon-tools-schema-data-design.html) ·
[Design Guide: The Conversation Surface](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-addon-conversation-surface.html)

## Dates (all Pacific Time)

| | |
|---|---|
| Submission closes | **Friday 23 October 2026, 12:00 pm** |
| Judging | Mon 9 Nov – Fri 20 Nov 2026 |
| Winners | on or around Thu 3 Dec 2026 |
| AWS $150 credits | **closed 7 October** (out of codes) |

No edits after the deadline except to remove infringing or personal
material.

## How it is judged

1. **Stage One, pass/fail:** the project "reasonably fits the theme and
   reasonably applies the required APIs/SDKs".
2. **Stage Two, four equally weighted criteria** (25 each):
   **Tech Implementation**, **Design**, **Potential Impact**,
   **Quality of the Idea**.
3. **Friction-log bonus:** up to **+10%**, assessed by Amazon's internal
   team and applied to the final score. Ties are broken by the highest
   score in criteria order (Tech first).
4. Judges "are not required to test the Project" and "may choose to judge
   based solely on the text description, images, and video". The video
   and README carry most of the weight.

### What the rules call obvious versus creative, for Alexa+

> **Obvious:** single-turn Q&A bot, basic MCP wrapper around an existing API.
> **Creative:** agentic workflow that orchestrates across services
> autonomously, **context-aware add-on that maintains state across
> sessions**, purchasing capabilities, media support (cards, carousels),
> MCP Apps, Agent Skills.

Sideline's defence against "basic wrapper around an existing API" is the
per-listener `last_told_at` state and the spoiler guard. Say that in the
first thirty seconds of the video; a live football feed alone is exactly
the "wrapper" the rules call obvious.

### AWS Builder and Open Source, same page

> **AWS Builder obvious:** single Bedrock call for text generation, S3 for
> storage. **Creative:** multi-service pipeline, agentic architecture,
> agent orchestration.
> **Open Source obvious:** README update, typo fix. **Creative:**
> meaningful feature addition with tests, bug fix that unblocks other
> developers, new integration pattern.

Sideline's Bedrock use is, honestly, closer to "a single Bedrock call"
than to a pipeline; what lifts it is the number of services doing real
work together (Bedrock, DynamoDB, Polly, Transcribe, Secrets Manager,
CloudWatch, App Runner) and the grounding guard.

## Submission requirements

- Text description of features and functionality.
- GitHub repo with all source, assets and setup/run instructions, either
  **public with an open-source licence detectable in the repo's About
  section**, or **private and shared** with the Amazon reviewers (below).
- For Alexa+: the repo must show the track technology "imported and
  actually called". An MCP server entry point satisfies this. The
  alternative **simulated Alexa+ experience** is exempt from that, but its
  source must be in the repo and the video must clearly show it.
- **Demo video, under 3 minutes**, public on YouTube or Vimeo, showing the
  project functioning on the platform it is for; **no third-party
  trademarks or copyrighted music or other material** without permission.
- **Product Feedback**, answering for each tool, API or SDK used:
  1. which tools/APIs/SDKs and for what,
  2. what worked well,
  3. what needs work,
  4. onboarding experience (zero to hello world),
  5. would you build with them again, **Yes/No and why**.
- Primary track(s) and mini challenge(s) selected.
- **AWS Builder:** describe the AWS services and how, *in the Product
  Feedback answer* (not only in the repo).
- **Open Source:** contribution URL, project repo URL, GitHub username,
  and what you did, how it works and why it matters. It must be a *new,
  additional* open-source project or a contribution (branch, fork or PR,
  merged or not) to a public repo, made in the window, *alongside* the
  primary submission.
- Optional: feature requests (priority Critical / Important /
  Nice-to-have) and friction-log entries.
- If the project predates 31 August: explain what was significantly
  updated in the window.
- "Third Party Integrations": you must be authorised to use any SDK, API
  or data under its terms.
- Testing: the project must be available free of charge for judges
  **until the judging period ends (20 Nov)**. Judges may require hardware
  access for projects on proprietary hardware.

### Private-repo reviewers

If the repo is private, add these as collaborators *at submission time*
(invitations expire after 7 days): `chris-trag`, `knmeiss`, `giolaq`,
`anishamalde`, `mosesroth`, `emersonsklar`; the rules also name the
Amazon Developer Relations email on the Devpost page.

## What Alexa+ itself requires of an MCP server

From the QuickStart and account-linking docs, which are stricter than the
Devpost rules:

- MCP **2025-11-25**, **Streamable HTTP**, HTTPS endpoint. Legacy HTTP+SSE
  is deprecated.
- **Round-trip response under 500 ms.** Sideline's Bedrock catch-up can
  take up to 3 s, so it *misses this target by design* unless
  `SIDELINE_BEDROCK_TIMEOUT` is lowered. See [BEDROCK.md](BEDROCK.md).
- Authentication, if you use account linking (optional, and partner-only: see the FAQ section below): see the table in
  [ALEXA_SETUP.md](ALEXA_SETUP.md). Notably the 401 must have **no**
  `WWW-Authenticate` header, and the *authorization server* must publish
  `/.well-known/oauth-authorization-server` with PKCE S256 or deployment
  is blocked.
- Add-on metadata: name ≤ 30 chars, short description ≤ 123, full ≤ 4000,
  3–4 example phrases, privacy policy and terms URLs (HTTPS), six icon
  sizes, a 600×900 carousel image.
- Tool design: one intent per tool, descriptions that say when to call it
  and what it returns, declare only parameters you honour, always return
  something (an error response, never nothing).
- Tools are cached until `alexa-ai deploy`.
- The QuickStart gives no regions or locales and does not state the CLI's
  package name; the FAQ explains why: the tooling is partner-only.

## The FAQ tab (read 2026-10-12): the part that changes the most

Source: [Devpost FAQs](https://amazonappdev2026.devpost.com/details/faqs).

- **The Alexa+ add-on tools are not available to participants.** "Category
  SDK, MCP Toolkit, CLI, and Web Simulator ... in preview and available to
  select partners only - there is currently no way for hackathon
  participants to apply". The QuickStart and setup pages above do not say
  so, which "has caused some confusion". So: no `alexa-ai`, no add-on
  deployment, no account linking, no Alexa developer-console simulator,
  and no way to connect to a real Alexa+ device. **This also answers the
  open question about regions: not available to anyone.**
- **What to do instead:** build the self-hosted MCP server and "demo it
  via your own web-based simulator or front end". A web page that acts as
  a real MCP client (initialize, tools/list, tools/call over Streamable
  HTTP) **satisfies the requirement**. "Showing an existing AI assistant
  app calling the same server is a nice bonus, but not required."
- **Hosting is not required.** "A locally runnable public repo plus your
  demo video is enough - judges can download, build, and test it
  themselves." The server "doesn't need to stay running after you
  submit". Spin AWS up to test and tear it down; mock Bedrock in early
  development. Lambda is suggested as cheap hosting.
- **Repo:** must be on **GitHub**. Public needs only an open-source
  licence file. Private: add `knmeiss`, `giolaq`, `anishamalde`,
  `mosesroth`, `emersonsklar` and the Devpost testing address
  (`testing@devpost.com`, decoded from the rules page), each must accept,
  invitations expire in 7 days. The rules page also names `chris-trag`.
- **Video media:** third-party media must be content you have rights to,
  and the video should "primarily demonstrate your own project". The FAQ
  invites you to "check with us on the specifics ... before finalizing".
- **Office hours:** Monday 19 October, 9:00 am PT (20:00 in Mauritius).
  Ask there, or in writing (rules §11), about the StatsBomb logo.

## Not found, so not claimed

- Hackathon-specific Alexa+ judging detail beyond the four criteria.
