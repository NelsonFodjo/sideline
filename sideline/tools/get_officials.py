"""Referee, assistants, card count.

Named once in a pre-match graphic and then effectively unavailable for
the next two hours. Cheap to build, and the thing blind fans mention
first when asked what they cannot find out.

No Bedrock - fast path, templated, under 300 ms.
"""


def run(ctx, args, listener_id):
    from . import resolve_fixture
    fx = resolve_fixture(ctx, args, listener_id)
    o = ctx.provider.officials(fx["fixture_id"])

    # If the provider does not give a running card count, derive it from
    # our own event log. We have the cards; there is no reason to make
    # the listener go without.
    if o.get("yellows_shown") is None:
        cards = [e for e in ctx.store.events(fx["fixture_id"]) if e["kind"] == "card"]
        o["yellows_shown"] = sum(1 for c in cards if c.get("colour") == "yellow")
        o["reds_shown"] = sum(1 for c in cards if c.get("colour") == "red")

    spoken = ctx.lang.templates.say_officials(o)
    structured = {"fixture_id": fx["fixture_id"], "officials": o,
                  "generated_by": "template"}
    return spoken, structured, None
