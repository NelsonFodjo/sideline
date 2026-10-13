"""How the listener likes answers: how much to say, and in which language."""

from ..mcp.errors import ToolError

_DETAIL = {"brief": "Okay, I'll keep answers brief.", "normal": "Okay, back to normal answers.",
           "full": "Okay, I'll give you more detail."}


def run(ctx, args, listener_id):
    detail, language = args.get("detail"), (args.get("language") or "").strip()
    if not detail and not language:
        raise ToolError("What would you like changed: how much I say, or the language?",
                        {"reason": "needs_choice"})
    rec = ctx.store.listener(listener_id)
    said = []
    if detail:
        rec["detail"] = detail
        said.append(_DETAIL[detail])
    if language:
        english = language.lower() in ("english", "en")
        rec["language"] = None if english else language
        said.append("Okay, I'll answer in English." if english else "Okay, I'll answer in %s." % language)
    ctx.store.save_listener(rec)
    return " ".join(said), {"detail": rec.get("detail"), "language": rec.get("language"),
                            "generated_by": "template"}, None
