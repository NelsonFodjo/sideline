# Submission checklist

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
- [ ] **Product feedback** on every tool, API and SDK used, including
      which AWS services and how. → `docs/PRODUCT_FEEDBACK.md`
- [ ] **Track and mini challenge selections**, with the extra fields each
      mini challenge requires.

## Worth the marks

- [ ] **Friction log** — task, steps, expected vs actual, severity,
      workaround, suggestion. Up to a 10% judging bonus.
      → `docs/FRICTION_LOG.md`
- [ ] **AWS Builder** — services named and documented.
      → `docs/MINI_CHALLENGES.md`
- [ ] **Open Source** — contribution URL, repo URL, GitHub username,
      short description of what and why.

## Timing traps

- [ ] **Send GitHub reviewer invitations at submission time, not before.**
      They expire after seven days. An invitation sent three weeks early
      has lapsed by judging. If one has lapsed, re-send from the same
      Collaborators page.
- [ ] **Redeploy the add-on after any tool description change.** The
      add-on caches the tool list; a changed description does nothing
      until `alexa-ai deploy` runs again.

## Before you press submit

- [ ] `make test` passes from a clean clone.
- [ ] `python3 -m sideline` works with no `.env`, no AWS, no key.
- [ ] No secrets in git history, not just in the working tree.
- [ ] Video is public, not unlisted-and-forgotten.
- [ ] Every link in the README resolves.
- [ ] The description does not claim anything the repo does not do.
