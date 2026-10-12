# Submission checklist

**Deadline: Friday 23 October 2026, 12:00 pm Pacific.** No edits after.
Everything below is checked against the official rules; see
[OFFICIAL_RULES.md](OFFICIAL_RULES.md) for the sources and what was *not*
found.

## Required

- [ ] **Text description** — what it does and how it works.
- [ ] **GitHub repository** with all source and run instructions.
      Either public with an open-source licence, or private and shared
      with the named Amazon reviewers.
- [ ] **The repo genuinely calls the technology in code** — an import, an
      entry point, a loaded MCP config. A README mention is explicitly
      not enough. *(Ours: `mcp/server.py` implements Streamable HTTP for
      spec 2025-11-25 and `tests/test_mcp_protocol.py` proves it.)*
- [ ] **Demo video under three minutes** — public, English, YouTube or
      Vimeo. No third-party trademarks or copyrighted music.
- [ ] **Product feedback** on every tool, API and SDK used, answering the
      five questions (what for, what worked, what needs work, onboarding,
      **build again Yes/No and why**). → `docs/PRODUCT_FEEDBACK.md`
- [ ] **AWS services described in the Product Feedback answer on the
      form**, not only in the repo. The rules say so explicitly.
- [ ] **Track and mini challenge selections**, with the extra fields each
      mini challenge requires.

## Worth the marks

- [ ] **Friction log** — task, steps, expected vs actual, severity,
      workaround, suggestion. Up to a 10% judging bonus.
      → `docs/FRICTION_LOG.md`
- [ ] **AWS Builder** — services named and documented.
      → `docs/MINI_CHALLENGES.md`
- [ ] **Open Source** — a *new, additional* open-source project or a
      contribution (branch, fork or PR) made in the window, alongside the
      primary submission. Contribution URL, repo URL, GitHub username,
      what / how / why. The sports-feed adapter is **not published yet**;
      if it will not be by the 23rd, drop this challenge or open a PR to
      an existing public repo instead.

## Timing traps

- [ ] **Prefer a public repo (MIT, licence visible in About):** it needs no
      invites at all. **If private**, add `knmeiss`, `giolaq`, `anishamalde`,
      `mosesroth`, `emersonsklar`, `chris-trag` and the Devpost testing
      address `testing@devpost.com` as collaborators.
      **Send GitHub reviewer invitations at submission time, not before.**
      They expire after seven days. An invitation sent three weeks early
      has lapsed by judging. If one has lapsed, re-send from the same
      Collaborators page.
- [ ] **Redeploy the add-on after any tool description change.** The
      add-on caches the tool list; a changed description does nothing
      until `alexa-ai deploy` runs again.

## Facts from the FAQ that shape the submission

- [ ] **Do not build around the Alexa+ add-on tools.** They are
      partner-only. The demo is your **web simulator acting as a real MCP
      client** over Streamable HTTP (`make run`, then open
      http://127.0.0.1:8765/). The FAQ says that satisfies the track.
- [ ] **Optional bonus:** show an existing AI assistant app calling the
      same MCP server.
- [ ] **Hosting is not required.** A locally runnable public repo plus the
      video is enough. If you do deploy, tear it down (`aws
      cloudformation delete-stack --stack-name sideline`).
- [ ] **Deadline in your time zone:** 12:00 pm PDT Friday 23 Oct is
      **23:00 in Mauritius**. Submit by 19:00 Mauritius time.
- [ ] **Office hours, Mon 19 Oct, 9:00 am PT (20:00 Mauritius):** ask about
      the StatsBomb logo and anything else you are unsure of.

## Before you press submit

- [ ] **Licence is detectable in the repo's About section** (public repo).
- [ ] **Video shows the project running on the platform it is for**, in
      under three minutes, with **no third-party trademarks**: no club
      badges, no league logos, and see the StatsBomb logo note in
      DATA_PROVIDERS.md.
- [ ] **Judges can reach it free until 20 November.** The default run
      needs no key and no AWS. If you host it, keep it up until then.
- [ ] **500 ms.** Alexa+ targets a 500 ms round trip. Decide
      `SIDELINE_BEDROCK_TIMEOUT` deliberately (BEDROCK.md).

- [ ] `make test` passes from a clean clone.
- [ ] `python3 -m sideline` works with no environment variables set: no AWS, no key.
- [ ] No secrets in git history, not just in the working tree.
- [ ] Video is public, not unlisted-and-forgotten.
- [ ] Every link in the README resolves.
- [ ] The description does not claim anything the repo does not do.
