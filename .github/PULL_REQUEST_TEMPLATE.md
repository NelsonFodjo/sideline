## What this changes

<!-- One or two sentences. Link the issue: "Fixes #12". -->

## Why

<!-- What a listener notices, or what a developer can now do. -->

## Checklist

- [ ] `make test` passes (offline: no network, no credentials)
- [ ] A test pins the new behaviour, or the PR says why none can
- [ ] The spoken answer still carries everything: nothing essential is only on screen
- [ ] A failure a listener can reach is a sentence a person would say
- [ ] New environment variables are in `sideline/config.py`, `.env.example` and `docs/ENVIRONMENT.md`
- [ ] Docs that describe the change are updated (`python3 scripts/check_links.py` passes)
- [ ] No new required dependency, and nothing in `sideline/` ships data files
