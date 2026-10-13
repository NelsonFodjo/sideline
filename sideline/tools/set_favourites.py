"""Remember the listener's teams: add, remove, clear, or read them back.

Only the names the listener gave are stored; nothing is invented. They are what
get_my_matches looks for, so "are my teams on" needs no team name.
"""

from ..mcp.errors import ToolError

MAX = 10


def _norm(name):
    return " ".join((name or "").split())


def run(ctx, args, listener_id):
    action = args.get("action")
    teams = [_norm(t) for t in (args.get("teams") or []) if _norm(t)]
    rec = ctx.store.listener(listener_id)
    mine = list(rec.get("favourites") or [])
    if action in ("add", "remove") and not teams:
        raise ToolError("Which team?", {"reason": "needs_teams"})
    if action == "add":
        for t in teams:
            if t.lower() not in [m.lower() for m in mine]:
                mine.append(t)
        mine = mine[:MAX]
        said = "Okay, I'll remember %s." % ", ".join(teams)
    elif action == "remove":
        mine = [m for m in mine if m.lower() not in [t.lower() for t in teams]]
        said = "Okay, I've forgotten %s." % ", ".join(teams)
    elif action == "clear":
        mine, said = [], "Okay, I've cleared your teams."
    else:
        said = ""
    if action != "list":
        rec["favourites"] = mine
        ctx.store.save_listener(rec)
    tail = ("Your teams: %s." % ", ".join(mine)) if mine else "You haven't told me any teams yet."
    return (said + " " + tail).strip(), {"favourites": mine, "generated_by": "template"}, None
