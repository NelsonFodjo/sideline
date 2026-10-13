"""Who is ruled out of the match, and why."""

from . import feed, resolve_fixture


def run(ctx, args, listener_id):
    team = (args.get("team") or "").strip()
    fx = resolve_fixture(ctx, args, listener_id, prefers="coming")
    out = feed(ctx, "injuries", fx["fixture_id"])
    if team:
        out = [o for o in out if team.lower() in (o.get("team") or "").lower()]
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
