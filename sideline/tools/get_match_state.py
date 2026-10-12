"""Score and clock. The most-asked question, so the fastest path.

No Bedrock. A scoreline is a fact; generating it adds latency and risk
and improves nothing. Target under 300 ms end to end.

Does NOT advance last_told_at. Hearing the score is not the same as
being told what happened - a listener who asks the score and then asks
what they missed must still get the goals.
"""


def run(ctx, args, listener_id):
    from . import resolve_fixture
    fx = resolve_fixture(ctx, args, listener_id)
    spoken = ctx.lang.templates.say_match_state(fx)

    structured = {
        "fixture_id": fx["fixture_id"],
        "home": fx["home"], "away": fx["away"],
        "score": fx["score"], "minute": fx.get("minute"),
        "status": fx.get("status"),
        "generated_by": "template",
    }
    ui = {"home": fx["home"], "away": fx["away"],
          "home_score": fx["score"]["home"], "away_score": fx["score"]["away"],
          "minute": fx.get("minute")}
    return spoken, structured, ui
