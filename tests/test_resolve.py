"""Understanding what a listener meant when the recogniser got it nearly right.

The AI offers a choice ("Arsenal against Chelsea, or Arsenal Women against
Everton?") and the listener answers with a name they do not say well. The
answer has to land on the option they were closest to, and only when it is
clear: a wrong guess spoken back as fact is worse than asking again, because
the listener cannot see the screen to notice. Names misheard inside a longer
sentence are repaired too, and ordinary words are never touched.
"""

from conftest import FOOTBALL, FOOTBALL_2, make_ctx

from sideline import resolve
from simulator import voice
from simulator import agent
from sideline.mcp.errors import ToolError
from sideline.tools import REGISTRY

FIXTURES = [{"home": "Newcastle Jets", "away": "Gamba Osaka"},
            {"home": "Kyoto Sanga", "away": "Ratchaburi"},
            {"home": "Pohang Steelers", "away": "Johor Darul Takzim FC"},
            {"home": "Shanghai SIPG", "away": "Daejeon Citizen"},
            {"home": "Manchester City", "away": "Leicester City"}]


def said(text, now=None):
    return resolve.snap("L", text, now=now)


def main():
    # ------------------------------------------------- answering a choice
    def offer():
        resolve.BOOK.remember("L", resolve.items_from_candidates(FIXTURES))

    cases = {                           # what the listener said -> who they meant
        "gamba": "Gamba Osaka", "gamma osaka": "Gamba Osaka",
        "new castle jets": "Newcastle Jets", "osaka": "Gamba Osaka",
        "kioto sanga": "Kyoto Sanga", "kyoto sanger": "Kyoto Sanga",
        "rat cha buri": "Ratchaburi", "pohan steelers": "Pohang Steelers",
        "pohang": "Pohang Steelers", "jo hor": "Johor Darul Takzim",
        "daejeon": "Daejeon Citizen", "dayjohn citizen": "Daejeon Citizen",
        "citizen": "Daejeon Citizen", "shanghai": "Shanghai SIPG",
    }
    for heard, meant in cases.items():
        offer()
        r = said(heard)
        assert r["changed"] and meant in r["text"] and " against " in r["text"], (heard, r)
        assert r["why"] in ("offer", "ordinal"), r
    print("ok  %d mispronounced answers each land on the option they were closest to" % len(cases))

    # said exactly right: acted on, but not "corrected" (nothing to announce)
    offer()
    r = said("Kyoto Sanga against Ratchaburi")
    assert not r["changed"] and r["text"] == "Kyoto Sanga against Ratchaburi"

    # ordinals
    for heard, i in (("the first one", 0), ("second", 1), ("number two", 1), ("three", 2)):
        offer()
        r = said(heard)
        assert r["why"] == "ordinal" and r["text"] == "%s against %s" % (
            FIXTURES[i]["home"], FIXTURES[i]["away"]), (heard, r)
    print("ok  'the first one', 'second', 'number two' pick by position")

    # ------------------------------------------------- when not to guess
    offer()
    for heard in ("city", "what's the score", "arsenal", "the other one"):
        offer()
        r = said(heard)
        assert not r["changed"], (heard, r)     # "city" is two options; the rest match none
    # two options about equally near: ask again, do not pick
    resolve.BOOK.remember("L", resolve.items_from_candidates(
        [{"home": "Arsenal", "away": "Chelsea"}, {"home": "Arsenal Women", "away": "Everton"}]))
    assert not said("arsenal")["changed"], "'arsenal' fits both: refuse, do not guess"
    print("ok  an answer that fits two options, or none, is left alone")

    # a question that happens to contain a name is not an answer to be replaced
    offer()
    r = said("what is the score in the Kyoto Sanga game please")
    assert r["text"].lower().startswith("what is the score"), r
    print("ok  a long sentence is not swallowed by an option")

    # offers expire, and are used up once answered
    resolve.BOOK.remember("L", resolve.items_from_candidates(FIXTURES), now=1000)
    assert not said("gamba", now=1000 + resolve.TTL_SECONDS + 1)["changed"], "expired"
    offer()
    assert said("gamba")["changed"] and not said("gamba")["changed"], "used up"
    print("ok  an offer is for the next thing said: it expires and is used once")

    # ----------------------------------------------- repairing names
    names = ["Bukayo Saka", "Martin Ødegaard", "Toby Alderweireld", "Héctor Bellerín", "Arsenal"]
    repair = {
        "What was the VAR decision on Bukaiyo Saka's goal?":
            "What was the VAR decision on Bukayo Saka's goal?",
        "Who is Martin Odegaard?": "Who is Martin Ødegaard?",
        "has Toby Alderweird been booked": "has Toby Alderweireld been booked",
        "is Hector Bellarin playing today": "is Héctor Bellerín playing today",
        "is Arsenel winning": "is Arsenal winning",
    }
    for heard, fixed in repair.items():
        r = resolve.snap("nobody", heard, names=names)
        assert r["text"] == fixed, (heard, r)
        # a different spelling is a correction worth showing; accents alone are not
        assert r["changed"] == (resolve._fold(fixed) != resolve._fold(heard)), (heard, r)
    for plain in ("what's the score", "tell me about that goal", "who is the captain",
                  "who is refereeing and what did I miss since halftime",
                  "kick-off just went", "has the substitution been made", "half time already"):
        r = resolve.snap("nobody", plain, names=names)
        assert not r["changed"], (plain, r)
    print("ok  misheard names are repaired; ordinary sentences are never touched")

    # ----------------------------------------- the real ambiguity, end to end
    ctx = make_ctx(replay=[FOOTBALL, FOOTBALL_2])
    try:
        REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "real")
        raise AssertionError("two Arsenal matches should be ambiguous")
    except ToolError as e:
        assert e.detail["reason"] == "ambiguous" and len(e.detail["candidates"]) == 2
        ambiguous = e

    # the agent keeps the candidates (they were being thrown away)
    def runner(name, args, lid):
        raise ambiguous
    _, is_err, record = agent._execute_tool("follow_match", {"team": "Arsenal"}, "real", runner)
    assert is_err and record["detail"]["candidates"], record

    resolve.learn(ctx, "real", {"text": "Which one?", "tool_results": [record]})
    labels = resolve.BOOK.labels("real")
    assert len(labels) == 2 and all(" against " in x for x in labels), labels
    hint = voice.vocabulary_hint(ctx, "real")
    assert hint.startswith("The listener is choosing between: " + labels[0]), hint
    got = resolve.understand(ctx, "real", "tottenham hot spur")
    assert got["changed"] and got["text"].startswith("Tottenham Hotspur against"), got
    assert "(fixture_id 1208342)" in got["agent_text"], \
        "the model is told which fixture, or it asks again with just a team name"
    assert "fixture_id" not in got["text"], "what the listener sees carries no id"
    print("ok  end to end: ambiguity -> the offer is remembered -> the recogniser is primed ->",
          "'tottenham hot spur' becomes", repr(got["text"]))

    # an open question with no list: the likely answers are today's teams
    resolve.BOOK.clear("open")
    resolve.learn(ctx, "open", {"text": "Which team do you want to follow?", "tool_results": []})
    assert resolve.BOOK.get("open"), "no list was given, so offer the teams playing today"
    r = resolve.understand(ctx, "open", "arsenel")
    assert r["changed"] and "Arsenal" in r["text"], r
    resolve.learn(ctx, "open", {"text": "It is two nil.", "tool_results": []})
    assert not resolve.BOOK.get("open"), "a plain statement offers nothing"
    print("ok  an open question is answered against the teams playing today")

    # understanding is a courtesy: it must never stop a question being answered
    class Broken(object):
        class store(object):
            @staticmethod
            def listener(_):
                raise RuntimeError("store down")
    r = resolve.understand(Broken(), "x", "what's the score")
    assert r["text"] == "what's the score" and not r["changed"]
    print("ok  a failure while understanding falls back to the words as heard")

    # A team nobody has followed is repaired too, from the teams on today ("Midtylland" for "Midtjylland").
    nobody = make_ctx()
    nobody.provider.fixtures_on = lambda off: [{"fixture_id": 7, "home": "FC Midtjylland", "away": "Brøndby IF",
                                                "status": "NS"}] if off == 0 else []
    r = resolve.understand(nobody, "fresh", "when does midtylland play")
    assert r["text"] == "when does Midtjylland play" and r["changed"] and r["why"] == "name", r
    r = resolve.understand(nobody, "fresh", "when does the match start")
    assert not r["changed"], "ordinary words are never touched"
    print("ok  a team heard a little off is repaired from the teams on today, even if nobody follows it")

    # Words we use ourselves are not misheard teams ("support" was heard as Porto, "player" as Bayer Leverkusen).
    for line in ("I support Arsenal", "who was the best player", "tell me about the players", "speak French"):
        r = resolve.snap("plain", line)
        assert not r["clarify"] and r["text"] == line, (line, r)
    assert resolve.snap("plain", "where is Arsenl in the league")["why"] == "name"        # a real slip is still repaired
    print("ok  ordinary words from our own tools' vocabulary never trigger a 'did you mean a team' question")

    print("\nresolve: all good")


if __name__ == "__main__":
    main()
