"""Past meetings between the two sides.

The least essential tool here, and included on purpose. A product that
only answers urgent questions feels like a utility; the friend on the
sofa also says "we never beat them at their place". Cheap, and it makes
the thing feel finished rather than clever.
"""


def run(ctx, args, listener_id):
    from . import resolve_fixture
    fx = resolve_fixture(ctx, args, listener_id, prefers="coming")
    limit = args.get("limit") or 5
    past = ctx.provider.head_to_head(fx["fixture_id"], limit)

    if not past:
        return ("I don't have their past meetings.",
                {"fixture_id": fx["fixture_id"], "results": [],
                 "generated_by": "template"}, None)

    lines = []
    for p in past:
        lines.append("%s %d, %s %d" % (p["home"], p["score"]["home"],
                                       p["away"], p["score"]["away"]))
    spoken = ("Their last meeting: %s." % lines[0]) if len(lines) == 1 else "Last %d meetings: %s." % (len(lines), "; ".join(lines))
    structured = {"fixture_id": fx["fixture_id"], "results": past,
                  "generated_by": "template"}
    return spoken, structured, None
