"""Who a player is: name, age, nationality, position, club, then what else can be asked.

The order is deliberate. A listener who says "tell me more about Nuno Mendes" wants to know who he is before anything
else, and to be asked what they want next, not to be read a match report. The feed has no honours or career titles, and
the answer says so: an assistant that skips what it lacks would sound as if there was nothing to say.
"""

from ..mcp.errors import ToolError
from . import feed

# ESPN gives the country ("Portugal"); a person is described by the adjective ("Portuguese").
_DEMONYM = {
    "argentina": "Argentine", "australia": "Australian", "austria": "Austrian", "belgium": "Belgian",
    "brazil": "Brazilian", "cameroon": "Cameroonian", "canada": "Canadian", "colombia": "Colombian",
    "croatia": "Croatian", "denmark": "Danish", "ecuador": "Ecuadorian", "egypt": "Egyptian",
    "england": "English", "france": "French", "germany": "German", "ghana": "Ghanaian",
    "ivory coast": "Ivorian", "italy": "Italian", "japan": "Japanese", "mexico": "Mexican",
    "morocco": "Moroccan", "netherlands": "Dutch", "nigeria": "Nigerian", "norway": "Norwegian",
    "poland": "Polish", "portugal": "Portuguese", "scotland": "Scottish", "senegal": "Senegalese",
    "serbia": "Serbian", "south korea": "South Korean", "spain": "Spanish", "sweden": "Swedish",
    "switzerland": "Swiss", "turkey": "Turkish", "ukraine": "Ukrainian", "united states": "American",
    "usa": "American", "uruguay": "Uruguayan", "wales": "Welsh", "algeria": "Algerian", "tunisia": "Tunisian",
    "mali": "Malian", "dr congo": "Congolese", "republic of ireland": "Irish", "northern ireland": "Northern Irish",
}


_PRONOUNS = {"male": ("he", "his"), "female": ("she", "her")}


def _age_phrase(age):
    """"a 24-year-old", "an 18-year-old"."""
    return "%s %d-year-old" % ("an" if str(age).startswith("8") or age in (11, 18) else "a", age)


def run(ctx, args, listener_id):
    player = (args.get("player") or "").strip()
    team = (args.get("team") or "").strip() or None
    p = feed(ctx, "player_profile", player, team)
    if not p:
        raise ToolError("I can't find a player called %s. Try the full name, or tell me his team." % player,
                        {"reason": "no_match", "player": player})
    name, club = p.get("name") or player, p.get("team")
    country = p.get("nationality")
    demonym = _DEMONYM.get((country or "").lower())

    # "Nuno Mendes is a 24-year-old Portuguese defender at Paris Saint-Germain, shirt number 25."
    position = p.get("position") or "player"
    words = []
    if p.get("age"):
        words.append(_age_phrase(p["age"]))
    else:
        words.append("an" if (demonym or position)[0].lower() in "aeiou" else "a")
    if demonym:
        words.append(demonym)
    words.append(position)
    line = "%s is %s" % (name, " ".join(words))
    if country and not demonym:
        line += " from %s" % country
    if club:
        line += " at %s" % club
    if p.get("number"):
        line += ", shirt number %s" % p["number"]
    spoken = line + "."

    # his / her / their: said as the feed says, "their" when it does not say
    they, their = _PRONOUNS.get(p.get("gender"), ("they", "their"))
    honours = p.get("honours")
    if honours:
        spoken += " Major titles: %s." % ", ".join(honours[:5])
    else:
        spoken += " I can't give %s major titles: my feed doesn't carry honours." % their
    spoken += " Want %s numbers this season, or how %s did in the latest match?" % (their, they)
    return spoken, {"player": p, "generated_by": "template"}, None
