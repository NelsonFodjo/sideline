"""Which competitions the feed covers. A free feed covers a few: this is how a listener finds out."""

from ..mcp.errors import ToolError
from . import feed

LISTED = 10


def run(ctx, args, listener_id):
    country = (args.get("country") or "").strip()
    comps = feed(ctx, "competitions", country or None)
    if not comps:
        raise ToolError("I can't see any competitions%s on this feed." % (" in %s" % country if country else ""),
                        {"reason": "no_match", "country": country})
    shown = comps[:LISTED]
    names = ["%s (%s)" % (c["name"], c["country"]) if c.get("country") else c["name"] for c in shown]
    spoken = "I can cover %s%s: %s." % (
        "%d competitions" % len(comps) if len(comps) > 1 else "one competition",
        " in %s" % country if country else "", ", ".join(names))
    if len(comps) > len(shown):
        spoken += " And %d more." % (len(comps) - len(shown))
    return spoken, {"competitions": shown, "total": len(comps), "generated_by": "template"}, None
