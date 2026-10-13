"""How each side has been doing: their last results, as words."""

from ..mcp.errors import ToolError
from . import feed, resolve_fixture

_WORDS = {"W": "won", "D": "drew", "L": "lost"}


def _say(form):
    return ", ".join(_WORDS[c] for c in (form or "").upper() if c in _WORDS)


def run(ctx, args, listener_id):
    fx = resolve_fixture(ctx, args, listener_id)
    form = feed(ctx, "form", fx["fixture_id"]) or {}
    home, away = _say(form.get("home")), _say(form.get("away"))
    if not home and not away:
        raise ToolError("I don't have recent form for this match.", {"reason": "no_match"})
    parts = []
    if home:
        parts.append("%s recently: %s." % (fx["home"], home))
    if away:
        parts.append("%s recently: %s." % (fx["away"], away))
    return " ".join(parts), {"form": form, "generated_by": "template"}, None
