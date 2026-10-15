import os
import sys

# The package sits at the repo root, so `python -m sideline` works from
# a clean clone with no install step and no PYTHONPATH. Tests only
# need the root on the path.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["SIDELINE_WEATHER"] = "off"       # no test reaches the network
os.environ["SIDELINE_BEDROCK"] = "off"       # unit tests run deterministic templates unless explicitly testing Bedrock

from sideline import language                       # noqa: E402
from sideline.app import Context                    # noqa: E402
from sideline.state import MemoryStore              # noqa: E402
from support import ReplayProvider                  # noqa: E402

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

# INVENTED fixtures (see tests/support.py). Never real data, never a demo.
FOOTBALL = os.path.join(_FIXTURES, "football-arsenal-tottenham.json")
FOOTBALL_2 = os.path.join(_FIXTURES, "football-tottenham-hotspur-arsenal.json")
BASKETBALL = os.path.join(_FIXTURES, "basketball-harbour-reef.json")


def make_ctx(start_minute=0, speed=0.0, replay=None):
    """A Context wired to a test double for the live feed.

    speed is zero by default so tests run deterministically; they
    call provider.jump_to() to position the match instead.
    """
    provider = ReplayProvider(replay or FOOTBALL, speed=speed, start_minute=start_minute)
    provider.jump_to(start_minute)
    return Context(provider, MemoryStore(), language)


def age_events(ctx, seconds=3600):
    """Pretend `seconds` of real time have passed since every logged event was first seen. jump_to() moves the match
    but not the clock, and an event first seen a moment ago is (rightly) still held back from a delayed listener."""
    for events in list(ctx.store._events.values()):
        for e in events:
            e["at"] -= seconds
            if e.get("happened_by"):
                e["happened_by"] -= seconds
