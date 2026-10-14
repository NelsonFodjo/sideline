"""Tests for the ESPN multi-sport live feed provider."""

import conftest  # noqa: F401
from sideline import providers
from sideline.providers.espn import EspnProvider
from sideline.mcp import registry


def main():
    p = EspnProvider()
    assert isinstance(providers.build(), EspnProvider), "build() defaults to EspnProvider"
    assert "fixtures" in p.capabilities and "events" in p.capabilities
    assert "lineups" in p.capabilities and "officials" in p.capabilities
    assert "standings" in p.capabilities and "injuries" in p.capabilities

    # Capabilities cover the full tool surface
    try:
        registry.limit_to(EspnProvider.capabilities)
        assert len(registry.public_tools()) == 27, "ESPN provider covers all 27 public MCP tools"
    finally:
        registry.limit_to(None)
    print("ok  ESPN capabilities cover all 27 tools")

    # Fixture normalization logic test
    sample_raw = {
        "id": "401915417",
        "date": "2026-10-13T19:00Z",
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "score": "3", "team": {"displayName": "Arsenal", "id": "359"}},
                {"homeAway": "away", "score": "0", "team": {"displayName": "Lille", "id": "367"}}
            ],
            "venue": {"fullName": "Emirates Stadium", "address": {"city": "London"}}
        }],
        "status": {"clock": 5400.0, "displayClock": "90'", "period": 2,
                   "type": {"name": "STATUS_FULL_TIME", "state": "post", "completed": True}}
    }
    fx = p._norm_fixture(sample_raw, "football", "uefa.champions")
    assert fx["fixture_id"] == "401915417"
    assert fx["home"] == "Arsenal" and fx["away"] == "Lille"
    assert fx["score"] == {"home": 3, "away": 0}
    assert fx["status"] == "FT"
    assert fx["minute"] == 90
    assert fx["sport"] == "football"
    print("ok  fixture normalization: teams, scores, elapsed minute, venue, status")

    # Soccer events normalization
    sample_summary = {
        "keyEvents": [
            {
                "type": {"text": "Goal"},
                "clock": {"displayValue": "64'"},
                "participants": [{"athlete": {"displayName": "Jurriën Timber"}, "team": {"displayName": "Arsenal"}}],
                "text": "Goal! Arsenal 1, Lille 0. Jurriën Timber right footed shot. Assisted by Noni Madueke."
            },
            {
                "type": {"text": "Yellow Card"},
                "clock": {"displayValue": "29'"},
                "participants": [{"athlete": {"displayName": "Mikel Merino"}, "team": {"displayName": "Arsenal"}}],
                "text": "Mikel Merino is shown the yellow card for a bad foul."
            },
            {
                "type": {"text": "Substitution"},
                "clock": {"displayValue": "65'"},
                "participants": [{"athlete": {"displayName": "Kai Havertz"}, "team": {"displayName": "Arsenal"}}],
                "text": "Substitution, Arsenal. Kai Havertz replaces Viktor Gyökeres."
            }
        ]
    }
    evs = p._soccer_events("401915417", sample_summary, since_minute=0)
    assert len(evs) == 3
    assert evs[0]["kind"] == "goal" and evs[0]["player"] == "Jurriën Timber" and evs[0]["assist"] == "Noni Madueke"
    assert evs[1]["kind"] == "card" and evs[1]["player"] == "Mikel Merino" and evs[1]["colour"] == "yellow"
    assert evs[2]["kind"] == "substitution" and evs[2]["player"] == "Kai Havertz" and evs[2]["player_off"] == "Viktor Gyökeres"
    print("ok  soccer events: goals with assists, yellow cards with reasons, substitutions with on and off")

    # Basketball events normalization
    sample_bball_summary = {
        "plays": [
            {
                "period": {"number": 1},
                "clock": {"displayValue": "11:46"},
                "scoreValue": 2,
                "scoringPlay": True,
                "text": "Kyrie Irving makes two point shot",
                "team": {"displayName": "Dallas Mavericks"}
            },
            {
                "period": {"number": 1},
                "clock": {"displayValue": "10:29"},
                "scoreValue": 3,
                "scoringPlay": True,
                "text": "Luka Doncic makes 26-foot three point jumper",
                "team": {"displayName": "Dallas Mavericks"}
            }
        ]
    }
    b_evs = p._basketball_events("401898400", sample_bball_summary, since_minute=0)
    assert len(b_evs) == 2
    assert b_evs[0]["kind"] == "basket" and b_evs[0]["points"] == 2 and b_evs[0]["player"] == "Kyrie Irving"
    assert b_evs[1]["kind"] == "basket" and b_evs[1]["points"] == 3 and b_evs[1]["player"] == "Luka Doncic"
    print("ok  basketball events: 2-pt and 3-pt baskets with points and player names")

    # Competitions discovery
    comps = p.competitions()
    assert any("Champions League" in c["name"] for c in comps)
    assert any("NBA" in c["name"] for c in comps)
    print("ok  competitions: soccer and basketball leagues listed")

    # Match stats normalization
    sample_stats_summary = {
        "boxscore": {
            "teams": [
                {
                    "team": {"displayName": "Arsenal"},
                    "statistics": [
                        {"name": "possessionPct", "displayValue": "62.4"},
                        {"name": "totalShots", "displayValue": "15"},
                        {"name": "shotsOnTarget", "displayValue": "7"},
                        {"name": "wonCorners", "displayValue": "6"},
                        {"name": "foulsCommitted", "displayValue": "8"},
                        {"name": "yellowCards", "displayValue": "1"},
                        {"name": "redCards", "displayValue": "0"},
                    ]
                },
                {
                    "team": {"displayName": "Lille"},
                    "statistics": [
                        {"name": "possessionPct", "displayValue": "37.6"},
                        {"name": "totalShots", "displayValue": "5"},
                        {"name": "shotsOnTarget", "displayValue": "2"},
                        {"name": "wonCorners", "displayValue": "3"},
                        {"name": "foulsCommitted", "displayValue": "12"},
                        {"name": "yellowCards", "displayValue": "2"},
                        {"name": "redCards", "displayValue": "0"},
                    ]
                }
            ]
        }
    }
    p._cache["https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/summary?event=401915417"] = (1e12, sample_stats_summary)
    p._event_meta["401915417"] = ("soccer", "football", "uefa.champions")
    m_stats = p.match_stats("401915417")
    assert "Arsenal" in m_stats and "Lille" in m_stats
    assert m_stats["Arsenal"]["possession"] == 62.4
    assert m_stats["Arsenal"]["shots"] == 15
    assert m_stats["Lille"]["fouls"] == 12
    print("ok  match_stats: possession, shots, on-target, corners, fouls, cards")

    # Form & H2H normalization
    sample_form_summary = {
        "lastFiveGames": [
            {
                "team": {"displayName": "Arsenal"},
                "events": [{"gameResult": "W"}, {"gameResult": "W"}, {"gameResult": "D"}, {"gameResult": "W"}, {"gameResult": "L"}]
            },
            {
                "team": {"displayName": "Lille"},
                "events": [{"gameResult": "L"}, {"gameResult": "D"}, {"gameResult": "W"}, {"gameResult": "L"}, {"gameResult": "W"}]
            }
        ],
        "seasonseries": [
            {
                "events": [
                    {
                        "date": "2026-03-01T15:00Z",
                        "competitors": [
                            {"homeAway": "home", "score": "2", "team": {"displayName": "Arsenal"}},
                            {"homeAway": "away", "score": "1", "team": {"displayName": "Lille"}},
                        ]
                    }
                ]
            }
        ]
    }
    p._cache["https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/summary?event=401915417"] = (1e12, sample_form_summary)
    form_res = p.form("401915417")
    assert form_res.get("home") == "LWDWW"
    assert form_res.get("away") == "WLWDL"
    h2h_res = p.head_to_head("401915417")
    assert len(h2h_res) == 1 and h2h_res[0]["home"] == "Arsenal" and h2h_res[0]["score"] == {"home": 2, "away": 1}
    print("ok  form & h2h: last 5 games sequence and head to head meetings")

    # Standings normalization
    sample_standings_doc = {
        "children": [
            {
                "standings": {
                    "entries": [
                        {
                            "team": {"id": "359", "displayName": "Arsenal"},
                            "stats": [
                                {"name": "rank", "value": 1},
                                {"name": "gamesPlayed", "value": 6},
                                {"name": "points", "value": 16},
                                {"name": "wins", "value": 5},
                                {"name": "ties", "value": 1},
                                {"name": "losses", "value": 0},
                                {"name": "pointsFor", "value": 14},
                                {"name": "pointsAgainst", "value": 3},
                            ]
                        }
                    ]
                }
            }
        ]
    }
    p._cache["https://site.api.espn.com/apis/v2/sports/soccer/eng.1/standings"] = (1e12, sample_standings_doc)
    tbl = p.standings("Premier League")
    assert len(tbl) >= 1
    assert tbl[0]["team"] == "Arsenal" and tbl[0]["position"] == 1 and tbl[0]["points"] == 16
    t_stats = p.team_stats("Arsenal")
    assert t_stats["team"] == "Arsenal" and t_stats["played"] == 6 and t_stats["won"] == 5
    print("ok  standings & team_stats: league table position, record, goals scored/conceded")

    # Squad normalization
    sample_roster = {
        "athletes": [
            {"displayName": "Bukayo Saka", "jersey": "7", "position": {"name": "Forward"}},
            {"displayName": "Martin Ødegaard", "jersey": "8", "position": {"name": "Midfielder"}},
            {"displayName": "David Raya", "jersey": "22", "position": {"name": "Goalkeeper"}},
        ],
        "coach": [{"displayName": "Mikel Arteta"}]
    }
    p._team_index["arsenal"] = ("soccer", "eng.1", "359", "Arsenal")
    p._cache["https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/teams/359/roster"] = (1e12, sample_roster)
    sq = p.squad("Arsenal")
    assert sq["team"] == "Arsenal"
    assert sq["coach"] == "Mikel Arteta"
    assert len(sq["players"]) == 3
    assert sq["players"][0]["name"] == "Bukayo Saka" and sq["players"][0]["number"] == "7"
    print("ok  squad: manager, player names, numbers, positions")

    # Top scorers normalization
    sample_stats_doc = {
        "stats": [
            {
                "name": "goalsLeaders",
                "leaders": [
                    {
                        "athlete": {"displayName": "Erling Haaland"},
                        "team": {"displayName": "Manchester City"},
                        "value": 10
                    }
                ]
            }
        ]
    }
    p._cache["https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/statistics"] = (1e12, sample_stats_doc)
    top = p.top_scorers("Premier League")
    assert len(top) == 1 and top[0]["player"] == "Erling Haaland" and top[0]["goals"] == 10
    print("ok  top_scorers: league leading scorers with goals and teams")

    print("\nespn provider: all good")


if __name__ == "__main__":
    main()
