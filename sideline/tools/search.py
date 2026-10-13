"""Find a team, player or competition by name.

A voice recogniser changes names, and a listener cannot see the spelling. This returns the
closest real names the feed knows, so a heard "asana" can be checked against what exists. It
answers nothing about a match: the other tools do that.
"""

from ..mcp.errors import ToolError
from . import feed

LISTED = 5


def run(ctx, args, listener_id):
    query = (args.get("query") or "").strip()
    kind = args.get("kind") or "team"
    hits = feed(ctx, "search", query, kind)[:LISTED]
    if not hits:
        raise ToolError("I couldn't find a %s called %s." % (kind, query),
                        {"reason": "no_match", "query": query, "kind": kind})
    said = []
    for h in hits:
        extra = " (%s)" % h["country"] if h.get("country") else ""
        said.append("%s%s" % (h["name"], extra))
    spoken = "I found %s: %s." % ("these" if len(said) > 1 else "this", ", ".join(said))
    return spoken, {"query": query, "kind": kind, "results": hits, "generated_by": "template"}, None
