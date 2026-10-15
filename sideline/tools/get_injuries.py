"""Who is ruled out of the match, and why."""

from ..mcp.errors import ToolError
from . import _is_team, feed, resolve_fixture


def run(ctx, args, listener_id):
    team = (args.get("team") or "").strip()
    fx = resolve_fixture(ctx, args, listener_id, prefers="coming")
    out = feed(ctx, "injuries", fx["fixture_id"])
    if out is None:                          # no report from the feed: saying "no one is out" would be a guess
        raise ToolError("I don't have an injury report for %s against %s." % (fx["home"], fx["away"]),
                        {"reason": "no_data", "fixture_id": fx["fixture_id"]})
    if team:
        out = [o for o in out if _is_team(o.get("team"), team)]
    if not out:
        return ("No one is reported out for %s." % ("%s against %s" % (fx["home"], fx["away"]) if not team else team),
                {"injuries": [], "generated_by": "template"}, None)
    by_team = {}
    for o in out:
        by_team.setdefault(o.get("team") or "", []).append(
            "%s%s" % (o["player"], " (%s)" % o["reason"].lower() if o.get("reason") else ""))
    spoken = " ".join("Out for %s: %s." % (t, ", ".join(names)) if t else "Out: %s." % ", ".join(names)
                      for t, names in by_team.items())
    return spoken, {"injuries": out, "generated_by": "template"}, None
