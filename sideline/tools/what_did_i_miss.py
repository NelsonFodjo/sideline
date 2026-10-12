"""The headline tool.

What this does that nothing else can: it reads the gap between when we
last told THIS listener something and now, and returns only that. Not a
match summary, not the last five minutes - their gap.

The listener never says how long they were away, because they should not
have to. Look at the inputSchema in registry.py: there is no time range
in the arguments. Alexa+ has no idea when the listener last heard
anything. We resolve the window from our own state.

Flow:
    1. gap_for()  - events since last_told_at, minus anything already told
    2. summaries.answer() - the paragraph: precomputed by the poller, or
       the template at once in demo mode; live mode waits for Bedrock
    3. mark_told() - move the marker, record the event ids

Step 3 is the one people forget. Without it the listener hears the same
goal every time they ask.
"""


# Beyond this, a full read-back stops being a catch-up and becomes a
# match report nobody can follow by ear. We switch to headlines and offer
# the rest - which is what the friend on the sofa does.
LONG_ABSENCE_MINUTES = 15


def run(ctx, args, listener_id, agent_mode=False):
    from . import resolve_fixture
    fx = resolve_fixture(ctx, args, listener_id)
    fid = fx["fixture_id"]

    events, frm, to = ctx.store.gap_for(listener_id, fid,
                                        since_minute=args.get("since_minute"))

    # Events that VAR later overturned are still told, but flagged - a
    # listener who heard the crowd needs to know it was chalked off.
    def flag(e):
        if e.get("superseded_by"):
            e = dict(e)
            e["detail"] = ((e.get("detail") or "") + " (later disallowed)").strip()
        return e
    events = [flag(e) for e in events]

    now = fx.get("minute") or to
    away = max(0, now - frm)
    long_absence = (away > LONG_ABSENCE_MINUTES and len(events) > 3
                    and not args.get("full"))

    mode = "milestones" if long_absence else "full"
    language = ctx.store.listener(listener_id).get("language")

    # Precomputed when possible, so the model is not on the listener's
    # clock; see sideline/summaries.py.
    from .. import summaries
    if agent_mode:
        # The agent needs the event facts, not a second model-generated
        # paragraph or a template that Nova would merely paraphrase.
        spoken, how, source = "", "tool-data", "not-generated"
    else:
        spoken, how, source = summaries.answer(ctx, mode, events, fx, frm, to,
                                               away, language)

    # When we only gave the headlines, do NOT mark the rest as told. The
    # listener was offered more and may ask for it, and a tool that
    # quietly consumed the events it did not read back would lose them.
    if mode == "milestones":
        key_ids = [e["id"] for e in events
                   if e["kind"] == "goal"
                   or (e["kind"] == "card" and e.get("colour") == "red")]
        ctx.store.mark_told(listener_id, frm, key_ids)
    else:
        ctx.store.mark_told(listener_id, max(to, now), [e["id"] for e in events])

    structured = {
        "fixture_id": fid,
        "home": fx.get("home"), "away": fx.get("away"), "minute": fx.get("minute"),
        "window": {"from_minute": frm, "to_minute": fx.get("minute") or to},
        "event_count": len(events),
        "mode": mode,
        "minutes_away": away,
        "events": [{"id": e["id"], "minute": e["minute"], "kind": e["kind"],
                    "player": e.get("player"), "team": e.get("team"),
                    "detail": e.get("detail")} for e in events],
        "score": fx["score"],
        # Reported honestly so anyone reading the response can see
        # whether a model was involved in producing the words.
        "generated_by": how,
        # Where the words came from: "precomputed" (cached model text, no
        # model call at ask time), "template-fast" (answered at once, the
        # model text queued for next time), "live" (model called now) or
        # "template" (no model configured).
        "summary_source": source,
    }
    ui = {"events": structured["events"], "score": fx["score"],
          "window": structured["window"]}
    return spoken, structured, ui
