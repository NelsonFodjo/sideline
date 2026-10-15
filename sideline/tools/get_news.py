"""The latest headlines on a team, a competition, or football in general; then the summary of one on request.

Headlines only, with how old each is: this is ESPN's news feed, not our own reporting, and a listener should be able to
tell a story from this morning from one from last week.
"""

import datetime

from ..mcp.errors import ToolError
from . import feed, ordinal

LISTED = 3


def _age(published, now=None):
    """"just now", "3 hours ago", "yesterday", "4 days ago" from an ISO time, or "" when it cannot be read."""
    try:
        then = datetime.datetime.fromisoformat((published or "").replace("Z", "+00:00"))
    except ValueError:
        return ""
    hours = ((now or datetime.datetime.now(datetime.timezone.utc)) - then).total_seconds() / 3600.0
    if hours < 1:
        return "just now"
    if hours < 24:
        n = int(hours)
        return "%d hour%s ago" % (n, "" if n == 1 else "s")
    days = int(hours // 24)
    return "yesterday" if days == 1 else "%d days ago" % days


def run(ctx, args, listener_id):
    team = (args.get("team") or "").strip() or None
    competition = (args.get("competition") or "").strip() or None
    news = feed(ctx, "news", team, competition, 5)
    if not news:
        about = team or competition or "football"
        raise ToolError("I can't find any news on %s right now." % about, {"reason": "no_news", "about": about})
    articles, scope = news["articles"], news["scope"]

    which = args.get("which")
    if which:                                        # "tell me about the second one"
        if not 1 <= which <= len(articles):
            raise ToolError("I only have %d headlines on %s." % (len(articles), scope), {"reason": "no_such_item"})
        a = articles[which - 1]
        spoken = "%s. %s" % (a["headline"], a.get("summary") or "ESPN gives no more than the headline.")
        return spoken, {"scope": scope, "article": a, "generated_by": "template"}, None

    items = []
    for i, a in enumerate(articles[:LISTED], 1):
        age = _age(a.get("published"))
        items.append("%s, %s%s" % (ordinal(i).capitalize(), a["headline"], ", %s" % age if age else ""))
    spoken = "The latest on %s, from ESPN: %s. Want more on any of them?" % (scope, ". ".join(items))
    return spoken, {"scope": scope, "articles": articles[:LISTED], "generated_by": "template"}, None
