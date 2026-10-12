# Contributing

## Read these two files first

1. [`sideline/state/store.py`](sideline/state/store.py) — the
   product is `last_told_at`. Everything else is plumbing.
2. [`sideline/mcp/registry.py`](sideline/mcp/registry.py) — tool
   descriptions are product surface, not documentation. A client reads
   them to choose a tool.

## Rules that are not negotiable

**Nothing essential lives only in the UI payload.** A listener on a
voice-only Echo must get the whole answer in `spoken_text`. This is an
accessibility product; a screen-only fact is a bug.

**Every failure the listener can reach is a sentence a person would
say.** `"I can't find Saka in this match."` — not `player_not_found`.

**`mark_told` never moves the marker backwards.** A listener hearing the
same goal twice is worse than hearing nothing.

**Fast tools do not call a model.** `get_match_state` and
`get_officials` stay template-only. A scoreline is a fact, and a model
call would only add latency and risk (server time is about 0.2 ms; see
docs/EVIDENCE.md).

**No new runtime dependencies.** Standard library only. boto3 (AWS paths)
and cryptography (RS256 auth) are the two optional exceptions. See ARCHITECTURE.md for why.

## Changing a tool description

Run `tests/test_routing_phrases.py`. It asserts the phrasings real
listeners use are still present, which is what breaks silently when
somebody tidies the wording.

(In a real Alexa+ deployment the add-on caches the tool list until
redeployed; that tooling is partner-only and is not used here.)

## Adding a provider

Subclass `providers/base.Provider`. Six methods. Honour the normalising
rules at the top of that file; they exist because every vendor gets the
same three things wrong.

## Tests

```bash
make test
```

No network, no credentials, no fixtures that flatter us. If a test needs
either, it is testing the wrong thing.
