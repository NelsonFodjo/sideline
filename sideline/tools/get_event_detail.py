"""One moment, in full.

Live commentary never lets you go back. A listener who half-heard a goal
while the kettle was on has no way to retrieve it. This reads one row
out of the durable event log, and it still works an hour later.

Resolution order: explicit id, then minute, then most recent of a kind.
"That goal" almost always means the last one.
"""

from ..mcp.errors import ToolError


def run(ctx, args, listener_id):
    from . import resolve_fixture
    fx = resolve_fixture(ctx, args, listener_id)
    events = ctx.store.events(fx["fixture_id"])
    if not events:
        raise ToolError("Nothing has happened in this match yet.",
                        {"reason": "no_events"})

    want_kind = args.get("kind")
    if want_kind in (None, "any"):
        want_kind = None

    chosen = None
    if args.get("event_id"):
        chosen = next((e for e in events if e["id"] == args["event_id"]), None)
    if not chosen and args.get("minute") is not None:
        m = args["minute"]
        pool = [e for e in events if not want_kind or e["kind"] == want_kind]
        # Nearest minute rather than exact: listeners say "that goal
        # around the half hour" and are usually a minute or two out.
        chosen = min(pool, key=lambda e: abs(e["minute"] - m)) if pool else None
    if not chosen:
        pool = [e for e in events if not want_kind or e["kind"] == want_kind]
        chosen = pool[-1] if pool else None

    if not chosen:
        raise ToolError("I can't find that moment in this match.",
                        {"reason": "not_found"})

    spoken = ctx.lang.templates.say_event(chosen)
    if chosen.get("superseded_by"):
        spoken += " It was later disallowed."
    spoken = spoken[0].upper() + spoken[1:] + "."

    ctx.store.mark_told(listener_id, fx.get("minute") or 0, [chosen["id"]])

    structured = {"fixture_id": fx["fixture_id"], "event": dict(chosen),
                  "generated_by": "template"}
    return spoken, structured, None
