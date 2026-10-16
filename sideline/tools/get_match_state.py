"""Score and clock. The most-asked question, so the fastest path.

No Bedrock. A scoreline is a fact; generating it adds latency and risk
and improves nothing. Target under 300 ms end to end.

Does NOT advance last_told_at. Hearing the score is not the same as
being told what happened - a listener who asks the score and then asks
what they missed must still get the goals.
"""


from .. import clock, sports
from ..status import FINISHED


def run(ctx, args, listener_id):
    from . import match_info, resolve_fixture
    if args.get("refresh"):
        # The listener doubts the score ("are you sure?", "check again"): forget what is kept and ask the feed now.
        fx0 = resolve_fixture(ctx, args, listener_id)
        if hasattr(ctx.provider, "invalidate"):
            ctx.provider.invalidate(fx0["fixture_id"])
        args = dict(args, fixture_id=fx0["fixture_id"])
    fx = resolve_fixture(ctx, args, listener_id)
    spoken = ctx.lang.templates.say_match_state(fx, fx)
    if not fx.get("series") and fx.get("sport") in ("basketball", "hockey", "baseball"):
        try:                                       # a playoff series is on the game's own page, not on a team's schedule
            fx["series"] = ctx.provider.series(fx["fixture_id"]) if hasattr(ctx.provider, "series") else None
        except Exception:                          # noqa: BLE001  a courtesy: the score stands without it
            fx["series"] = None
    if fx.get("series"):
        spoken += " %s." % fx["series"].rstrip(".")
    if fx.get("score_unconfirmed"):
        spoken += " I can't be sure that is where your screen is."

    sp = sports.for_fixture(fx)
    minute = fx.get("minute")
    if minute is not None and fx.get("status") in FINISHED and minute > sp.regulation_minutes and sp.key != "football":
        minute = sp.regulation_minutes                 # a finished game is at the end of its clock, not at football's 90
    structured = {
        "fixture_id": fx["fixture_id"],
        "home": fx["home"], "away": fx["away"],
        "score": fx["score"], "minute": minute,
        # The clock, so a screen can draw this sport as it is: four quarters of 12 minutes, three periods of 20, nine innings.
        "sport": sp.key, "regulation_minutes": sp.regulation_minutes, "period_minutes": sp.period_minutes,
        "period_word": sp.period_word, "score_word": sp.score_word,
        "status": fx.get("status"),
        "generated_by": "template",
        # Whether this is the match the listener follows (a client keeps showing a followed match until it is switched or stopped).
        "following": ctx.store.listener(listener_id).get("following") == fx["fixture_id"],
        # The time now and the fixture's start: "when does it kick off?"
        "clock": clock.snapshot(fx),
        "match": match_info(fx),
        "series": fx.get("series"),
        # How far behind the live match this listener's picture is, and whether the held-back score could be placed.
        "delay_seconds": int(fx.get("broadcast_offset") or 0),
        "score_unconfirmed": bool(fx.get("score_unconfirmed")),
    }
    ui = {"home": fx["home"], "away": fx["away"],
          "home_score": fx["score"]["home"], "away_score": fx["score"]["away"],
          "minute": fx.get("minute")}
    return spoken, structured, ui
