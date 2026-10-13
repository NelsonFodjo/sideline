"""Referee, assistants and the running discipline count (cards in football,
fouls in basketball; see sideline/sports/).

Named once in a pre-match graphic and then effectively unavailable for
the next two hours. Cheap to build, and the thing blind fans mention
first when asked what they cannot find out.

No Bedrock - fast path, templated, under 300 ms.
"""


from .. import sports


def run(ctx, args, listener_id):
    from . import resolve_fixture
    fx = resolve_fixture(ctx, args, listener_id)
    o = ctx.provider.officials(fx["fixture_id"])

    # If the provider does not give a running card count, derive it from
    # our own event log. We have the cards; there is no reason to make
    # the listener go without.
    sp = sports.for_fixture(fx)
    first = (sp.official_count_keys or [None])[0]
    if first and o.get(first) is None:
        o.update(sp.official_counts(ctx.store.events(fx["fixture_id"])))

    spoken = ctx.lang.templates.say_officials(o, fx)
    structured = {"fixture_id": fx["fixture_id"], "officials": o,
                  "generated_by": "template"}
    return spoken, structured, None
