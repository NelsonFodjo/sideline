# Contributing

## Read these two files first

1. [`sideline/state/store.py`](sideline/state/store.py): the product is
   `last_told_at`. Everything else is plumbing.
2. [`sideline/mcp/registry.py`](sideline/mcp/registry.py): tool descriptions are
   product surface, not documentation. A client reads them to choose a tool.

## Rules that are not negotiable

**Nothing essential lives only in the UI payload.** A listener on a voice-only
device must get the whole answer in the spoken text. This is an accessibility
product; a screen-only fact is a bug.

**Every failure the listener can reach is a sentence a person would say.**
"I can't find Saka in this match", not `player_not_found`.

**`mark_told` never moves the marker backwards.** Hearing the same goal twice is
worse than hearing nothing.

**Fast tools do not call a model.** `get_match_state` and `get_officials` stay
template-only. A scoreline is a fact; a model call only adds latency and risk.

**If Bedrock is on, a failure is reported, never papered over with canned
wording.** If it is off, the template is used and labelled `generated_by: template`.

**No new required dependencies.** The server is standard-library Python. boto3
and the Nova Sonic SDK are optional and the product degrades without them.

**No recorded or demo data in the product.** Sideline reads the live feed. Tests
use small, labelled-invented fixtures in `tests/fixtures/`, and nothing in `sideline/`
may ship data files.

**Test data never touches a real table.** A server built with a test provider uses memory state only, whatever
`SIDELINE_STATE` says (`app.build`), and `tests/test_finder.py` pins it. Invented fixtures once ended up in the app's own
DynamoDB table and made every match question fail (FL-17).

**No environment variable without a reader, and no reader without documentation.**
`sideline/config.py` `VARIABLES` is the registry; `tests/test_environment.py`
fails if the code, that list, `.env.example` and `docs/ENVIRONMENT.md` disagree.

## Changing a tool description

Run `tests/test_routing_phrases.py`. It asserts the phrasings real listeners use
are still present, which is what breaks silently when somebody tidies the wording.

## Adding a provider or a sport

A provider subclasses `providers/base.Provider` and honours the normalising rules
at the top of that file. A sport is a `SportProfile` ([docs/SPORTS.md](docs/SPORTS.md)).

## Tests

```bash
make test
```

No network, no credentials. If a test needs either, it is testing the wrong thing.
