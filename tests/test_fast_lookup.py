"""One team lookup is two requests, not 116; and a feed that is down says an error occurred, not "no matches".

The schedule sample is a real ESPN team-schedule response (Paris Saint-Germain, three events, one of them the
Champions League match at Manchester City, 4-2 to PSG), trimmed to three events.
"""

import json
import os
import threading
import time
import urllib.request

from sideline.mcp import server as mcp_server
from sideline.mcp.errors import ERROR_SPOKEN
from sideline.providers.base import ProviderUnavailable
from sideline.providers.espn import EspnProvider

HERE = os.path.dirname(os.path.abspath(__file__))
SEARCH = {"results": [{"contents": [
    {"displayName": "Paris Saint-Germain", "uid": "s:600~t:19258", "sport": "soccer", "defaultLeagueSlug": "fra.w.1"},
    {"displayName": "Paris Saint-Germain", "uid": "s:600~t:160", "sport": "soccer", "defaultLeagueSlug": "fra.1"}]}]}


def main():
    with open(os.path.join(HERE, "fixtures", "espn-team-schedule-sample.json")) as fh:
        schedule = json.load(fh)

    with open(os.path.join(HERE, "fixtures", "espn-team-schedule-with-upcoming.json")) as fh:
        with_upcoming = json.load(fh)

    def fake(url, ttl=None, strict=False):
        urls.append(url)
        if "search/v2" in url:
            return SEARCH
        return with_upcoming if "fixture=true" in url else schedule      # ESPN: played, or (fixture=true) still to come
    p = EspnProvider()
    urls = []
    p._fetch_json = fake
    got = p.team_matches("Paris Saint-Germain", days_back=3650, days_ahead=30)
    assert len(urls) == 3, urls
    assert any("teams/160/schedule?fixture=true" in u for u in urls) and any(u.endswith("teams/160/schedule") for u in urls), urls
    assert all("/soccer/all/" in u for u in urls[1:]) and not any("t:19258" in u or "19258" in u for u in urls), urls
    print("ok  a team lookup is a search and two schedules (played, coming): %d requests, not 116" % len(urls))

    latest = got["recent"][0]
    assert (latest["home"], latest["away"]) == ("Manchester City", "Paris Saint-Germain"), latest
    assert latest["score"] == {"home": 2, "away": 4} and latest["status"] == "FT", latest
    assert latest["fixture_id"] == "401915407" and latest["competition"] == "UEFA Champions League", latest
    kickoffs = [f["kickoff"] for f in got["recent"]]
    assert kickoffs == sorted(kickoffs, reverse=True), "latest first"
    print("ok  the Champions League match is found, 4-2, newest first:", latest["home"], "v", latest["away"])

    # the NEXT match, and the last one, both from the same lookup
    nxt = got["upcoming"]
    assert nxt, "a team with matches to come must have them listed"
    assert [f["kickoff"] for f in nxt] == sorted(f["kickoff"] for f in nxt), "soonest first"
    assert "Strasbourg" in (nxt[0]["home"], nxt[0]["away"]) and nxt[0]["kickoff"].startswith("2026-10-17"), nxt[0]
    assert nxt[0]["status"] == "NS" and nxt[0]["competition"] == "Ligue 1", nxt[0]
    print("ok  the next match is found: %s v %s on %s (%s)" % (nxt[0]["home"], nxt[0]["away"], nxt[0]["kickoff"][:10], nxt[0]["competition"]))

    # the feed is down: that is an error, never "no matches"
    def down(url, ttl=None, strict=False):
        raise ProviderUnavailable("down")
    p2 = EspnProvider()
    p2._fetch_json = down
    for call in (lambda: p2.team_matches("Paris Saint-Germain"), lambda: p2.fixtures_on(0)):
        try:
            call()
            raise AssertionError("an outage must not look like an empty answer")
        except ProviderUnavailable:
            pass
    print("ok  an unreachable feed raises instead of answering 'no matches'")

    # what the listener hears, through a real server: a down feed and a crashing tool say the same sentence
    def run_tool(name, args, listener):
        if args.get("query") == "feed":
            raise ProviderUnavailable("ESPN is down")
        raise RuntimeError("secret internal detail")
    port = 8843
    srv = mcp_server.serve("127.0.0.1", port, run_tool, lambda h: "t", ["*"])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)

    def post(payload, headers=None):
        req = urllib.request.Request("http://127.0.0.1:%d/mcp" % port, data=json.dumps(payload).encode(),
                                     headers=dict({"Content-Type": "application/json"}, **(headers or {})))
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.headers, json.loads(r.read() or b"{}")
    try:
        head, _ = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
        sid = {"Mcp-Session-Id": head["Mcp-Session-Id"], "MCP-Protocol-Version": "2025-11-25"}
        for args in ({"query": "feed"}, {"query": "crash"}):
            _, doc = post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                           "params": {"name": "search", "arguments": args}}, sid)
            result = doc["result"]
            assert result["isError"] is True and result["content"][0]["text"] == ERROR_SPOKEN, result
            assert "secret internal detail" not in json.dumps(result), "a crash must not leak its detail: %s" % result
    finally:
        srv.shutdown()
    assert "error occurred" in ERROR_SPOKEN and "rephras" in ERROR_SPOKEN and "later" in ERROR_SPOKEN
    print("ok  a down feed and a crashing tool both say: " + ERROR_SPOKEN)


if __name__ == "__main__":
    main()
    print("\nfast lookup: all good")
