#!/usr/bin/env python3
"""Ask the MCP tools questions yourself, against LIVE ESPN. Wording is by template (no model, no AWS).

    python3 scripts/ask.py                 # live ESPN, the real provider the server uses
    python3 scripts/ask.py --replay        # the invented fixtures instead, offline and deterministic

You type a tool and its arguments as JSON; it prints what a listener would hear, then what it cost:
the ESPN requests that really went over the network (cache hits are free) and the time taken.

    get_fixtures {"competition": "Champions League", "when": "yesterday"}
    get_match_state {"team": "Arsenal"}
    get_standings {"competition": "Premier League"}
    follow_match {"team": "Arsenal"}       then what_did_i_miss, get_player_context {"player": "he"} ...

    :follow Arsenal        follow a match as this listener (what_did_i_miss and the spoiler guard need it)
    :delay 0|45|default    this listener's delay in seconds
    :urls                  show the requests of the last answer      :tools   list tools
    :help                  this text                                 :quit

Free-form speech ("who's winning?") needs the model: use `make run` and the simulator, or scripts/route_check.py.
Public ESPN endpoints, read-only. A session reuses one provider, so a repeated question shows the warm cost.
"""

import json
import logging
import os
import sys
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
os.environ.setdefault("SIDELINE_STATE", "memory")
os.environ.setdefault("SIDELINE_LOG_DIR", "off")
os.environ["SIDELINE_BEDROCK"] = "off"

from sideline import language                      # noqa: E402
from sideline.app import Context                   # noqa: E402
from sideline.mcp.errors import ERROR_SPOKEN, ToolError   # noqa: E402
from sideline.providers.base import ProviderUnavailable   # noqa: E402
from sideline.state import MemoryStore             # noqa: E402
from sideline.tools import REGISTRY                # noqa: E402

WHO = "you"


class Failures(logging.Handler):
    """Counts the feed requests that failed: they leave nothing in the cache, so the cache cannot show them."""

    def __init__(self):
        logging.Handler.__init__(self)
        self.lines = []

    def emit(self, record):
        msg = record.getMessage()
        if "ESPN" in msg and "failed" in msg:
            self.lines.append(msg)


class Session(object):
    def __init__(self, replay):
        self.replay = replay
        if replay:
            sys.path.insert(0, os.path.join(ROOT, "tests"))
            from conftest import FOOTBALL, make_ctx
            self.ctx = make_ctx(start_minute=64, replay=FOOTBALL)
            print("-- invented fixtures: Arsenal v Tottenham at 64'")
        else:
            from sideline.providers.espn import EspnProvider
            self.ctx = Context(EspnProvider(), MemoryStore(), language)
            print("-- live ESPN")
        self.failures = Failures()
        logging.getLogger().addHandler(self.failures)
        self.last_urls = []

    def _made(self):
        return getattr(self.ctx.provider, "request_count", 0)

    def command(self, line):
        parts = line.split(None, 1)
        word, arg = parts[0], (parts[1] if len(parts) > 1 else "")
        if word == ":follow" and arg:
            self.ask("follow_match " + json.dumps({"team": arg}))
        elif word == ":delay" and (arg == "default" or arg.isdigit()):
            rec = self.ctx.store.listener(WHO)
            rec["broadcast_offset"] = None if arg == "default" else int(arg)
            self.ctx.store.save_listener(rec)
            print("-- delay %s" % ("default" if arg == "default" else arg + "s"))
        elif word == ":urls":
            print("\n".join("  " + u for u in self.last_urls) or "  (none: answered from the cache)")
        elif word == ":tools":
            print(", ".join(sorted(REGISTRY)))
        elif word == ":help":
            print(__doc__)
        else:
            print("unknown command, try :help")

    def ask(self, line):
        name, _, raw = line.partition(" ")
        if name not in REGISTRY:
            print("no tool called %r. :tools lists them." % name)
            return
        try:
            args = json.loads(raw) if raw.strip() else {}
        except ValueError:
            print("the arguments must be JSON, e.g. get_standings {\"competition\": \"Premier League\"}")
            return
        before = self._made()
        failed_before = len(self.failures.lines)
        started = time.time()
        table, teams = None, ("Home", "Away")
        try:
            spoken, structured, _ = REGISTRY[name](self.ctx, args, WHO)
            table = (structured or {}).get("table")
            teams = ((structured or {}).get("home") or "Home", (structured or {}).get("away") or "Away")
        except ToolError as e:
            spoken = e.spoken
        except ProviderUnavailable:
            spoken = ERROR_SPOKEN                       # what the server says when the feed cannot be reached
        except Exception as e:                          # noqa: BLE001 - show it, this is a probing tool
            spoken = "%s\n  (probe: the tool raised %s: %s)" % (ERROR_SPOKEN, type(e).__name__, e)
        elapsed = (time.time() - started) * 1000.0
        self.last_urls = [u for n, u in getattr(self.ctx.provider, "_requests", ()) if n > before]
        failed = len(self.failures.lines) - failed_before
        print("\n  " + (spoken or "(nothing to say)") + "\n")
        if table and all("metric" in r for r in table):        # a statistics table; other lists are just spoken
            width = max(len(r["metric"]) for r in table)
            col = max([len(teams[0])] + [len(str(r["home"])) for r in table])
            print("  %-*s  %-*s  %s" % (width, "Metric", col, teams[0], teams[1]))
            for r in table:
                print("  %-*s  %-*s  %s" % (width, r["metric"], col, r["home"], r["away"]))
            print()
        if not self.replay:
            print("  [%d ESPN request%s%s, %.0f ms. :urls to see them]\n" % (
                len(self.last_urls), "" if len(self.last_urls) == 1 else "s",
                (", %d failed attempt%s" % (failed, "" if failed == 1 else "s")) if failed else "", elapsed))


def main():
    replay = "--replay" in sys.argv[1:]
    print(__doc__.split("\n\n")[0] + "\n(:help for commands, :quit to leave)\n")
    session = Session(replay)
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if line in (":quit", ":q", "quit", "exit"):
            return
        session.command(line) if line.startswith(":") else session.ask(line)


if __name__ == "__main__":
    main()
