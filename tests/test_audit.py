"""The logs folder: daily files, a JSON line per call, secrets never in them, old files pruned.

Runs in a temporary directory. Pinned: nothing is written when logs are off, a token in an argument or an
error is replaced with ***, files older than the retention are deleted and today's is kept, and a real tool
call through the MCP server leaves one line with its tool, arguments, outcome and speed.
"""

import datetime
import json
import logging
import os
import tempfile

from conftest import make_ctx

from sideline import audit
from sideline.mcp import server as mcp_server
from sideline.mcp.errors import ToolError
from sideline.providers.base import ProviderUnavailable
from sideline.tools import REGISTRY


def lines(directory, kind="calls", ext="jsonl"):
    path = os.path.join(directory, "%s-%s.%s" % (kind, datetime.date.today().isoformat(), ext))
    return [l for l in open(path, encoding="utf-8").read().split("\n") if l]


def main():
    # off: nothing is written, nothing breaks
    assert audit.setup("off") is None
    audit.record("tool", tool="x")                        # a no-op, never an error
    print("ok  with logs off, recording does nothing")

    with tempfile.TemporaryDirectory() as tmp:
        directory = audit.setup(os.path.join(tmp, "logs"), keep_days=3)
        assert directory and os.path.isdir(directory), "the folder is created"

        # secrets are replaced wherever they would appear
        os.environ["SPORTMONKS_TOKEN"] = "tok_1234567890_secret"
        audit.record("tool", tool="x", args={"q": "hello tok_1234567890_secret"}, problem="bad token tok_1234567890_secret")
        logging.getLogger("sideline.test").warning("calling with tok_1234567890_secret now")
        row = json.loads(lines(directory)[0])
        assert "tok_1234567890_secret" not in json.dumps(row) and "***" in row["args"]["q"] and "***" in row["problem"], row
        text = "\n".join(lines(directory, "sideline", "log"))
        assert "tok_1234567890_secret" not in text and "calling with *** now" in text, text
        os.environ.pop("SPORTMONKS_TOKEN")
        assert row["kind"] == "tool" and row["time"].count(":") >= 2, "a timestamped line"
        print("ok  one JSON line per record and a text log; a secret is replaced with *** in both")

        # retention
        for days_ago, kind, ext in ((10, "calls", "jsonl"), (5, "sideline", "log"), (2, "calls", "jsonl")):
            day = (datetime.date.today() - datetime.timedelta(days=days_ago)).isoformat()
            open(os.path.join(directory, "%s-%s.%s" % (kind, day, ext)), "w").write("old\n")
        open(os.path.join(directory, "notes.txt"), "w").write("not ours\n")
        removed = audit.prune()
        left = sorted(os.listdir(directory))
        assert len(removed) == 2 and "notes.txt" in left, (removed, left)
        assert any(n.startswith("calls-%s" % (datetime.date.today() - datetime.timedelta(days=2))) for n in left)
        assert any(n.startswith("calls-%s" % datetime.date.today()) for n in left), "today's file stays"
        print("ok  files older than the retention are deleted; recent ones and strangers' files are kept")

        # a real tool call through the server leaves its line
        ctx = make_ctx(start_minute=40)
        dispatcher = mcp_server.Dispatcher(
            lambda name, args, listener, agent=False: REGISTRY[name](ctx, args, listener), mcp_server.Sessions())
        dispatcher._call({"name": "follow_match", "arguments": {"team": "Arsenal"}}, "ann")
        try:
            def refuse(*a, **k):
                raise ProviderUnavailable("rateLimit: slow down")
            mcp_server.Dispatcher(refuse, mcp_server.Sessions())._call({"name": "get_match_state", "arguments": {}}, "ann")
            def decline(*a, **k):
                raise ToolError("Which match?", {"reason": "no_fixture"})
            mcp_server.Dispatcher(decline, mcp_server.Sessions())._call({"name": "get_match_state", "arguments": {}}, "ann")
        finally:
            pass
        rows = [json.loads(l) for l in lines(directory) if '"tool"' in l]
        mine = [r for r in rows if r.get("tool") in ("follow_match", "get_match_state")]
        assert [r["ok"] for r in mine] == [True, False, False], mine
        assert mine[0]["args"] == {"team": "Arsenal"} and mine[0]["ms"] >= 0 and "Arsenal" in mine[0]["spoken"]
        assert mine[1]["reason"] == "provider_unavailable" and "slow down" in mine[1]["problem"]
        assert mine[2]["reason"] == "no_fixture" and mine[2]["spoken"] == "Which match?"
        print("ok  a tool call, a feed refusal and a decline each leave a line with tool, arguments, outcome and speed")

        audit.setup("off")
    print("\naudit: all good")


if __name__ == "__main__":
    main()
