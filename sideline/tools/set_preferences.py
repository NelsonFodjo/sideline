"""How the listener likes answers: how much to say, preferred sport, and in which language. Or: forget everything."""

from .. import sports
from ..mcp.errors import ToolError

_DETAIL = {"brief": "Okay, I'll keep answers brief.", "normal": "Okay, back to normal answers.",
           "full": "Okay, I'll give you more detail."}


def run(ctx, args, listener_id):
    detail = args.get("detail")
    language = (args.get("language") or "").strip()
    sport = (args.get("sport") or "").strip().lower()
    if sport in ("soccer", "association football"):
        sport = "football"
    if args.get("forget") == "everything":
        ctx.store.forget_listener(listener_id)
        return ("Done. I've forgotten your teams, your settings and what you'd heard. Name a team or a match to start again.",
                {"forgotten": True, "generated_by": "template"}, None)
    if not detail and not language and not sport:
        known = " or ".join(sports.known())
        raise ToolError("What would you like changed: your sport (%s), how much I say, or the language?" % known,
                        {"reason": "needs_choice", "sports": sports.known(), "fork": sports.known()})
    rec = ctx.store.listener(listener_id)
    said = []
    if sport:
        if sport in sports.known():
            rec["sport"] = sport
            said.append("Okay, I'll focus on %s." % sport)
        else:
            raise ToolError("I only cover %s." % " and ".join(sports.known()),
                            {"reason": "unknown_sport", "sports": sports.known()})
    if detail:
        rec["detail"] = detail
        said.append(_DETAIL[detail])
    if language:
        english = language.lower() in ("english", "en")
        rec["language"] = None if english else language
        said.append("Okay, I'll answer in English." if english else "Okay, I'll answer in %s." % language)
    ctx.store.save_listener(rec)
    return " ".join(said), {"detail": rec.get("detail"), "language": rec.get("language"),
                            "sport": rec.get("sport"), "generated_by": "template"}, None
