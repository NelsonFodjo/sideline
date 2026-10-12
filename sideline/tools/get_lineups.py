"""Line-ups, formation and bench.

The graphic that is on screen for eight seconds before kick-off and is
never read aloud. Listeners ask for this late and often, which is why
it is its own tool rather than part of a general match-info tool.

Advances last_told_at, because answering it means we have spoken to the
listener about this match at this minute - and the catch-up window
should start from here.
"""


def run(ctx, args, listener_id):
    from . import resolve_fixture
    fx = resolve_fixture(ctx, args, listener_id)
    lineups = ctx.provider.lineups(fx["fixture_id"])
    team = args.get("team")

    spoken = ctx.lang.templates.say_lineups(lineups, team)
    ctx.store.mark_told(listener_id, fx.get("minute") or 0)

    structured = {"fixture_id": fx["fixture_id"], "lineups": lineups,
                  "generated_by": "template"}
    ui = {"lineups": lineups}
    return spoken, structured, ui
