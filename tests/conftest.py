import os
import sys

# The package sits at the repo root, so `python -m sideline` works from
# a clean clone with no install step and no PYTHONPATH. Tests only
# need the root on the path.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sideline import language                       # noqa: E402
from sideline.app import Context                    # noqa: E402
from sideline.state import MemoryStore              # noqa: E402
from support import ReplayProvider                  # noqa: E402

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

# INVENTED fixtures (see tests/support.py). Never real data, never a demo.
FOOTBALL = os.path.join(_FIXTURES, "football-arsenal-tottenham.json")
FOOTBALL_2 = os.path.join(_FIXTURES, "football-tottenham-hotspur-arsenal.json")
BASKETBALL = os.path.join(_FIXTURES, "basketball-harbour-reef.json")


def make_ctx(start_minute=0, speed=10000.0, replay=None):
    """A Context wired to a test double for the live feed.

    speed is enormous by default so tests do not wait on a clock; they
    call provider.jump_to() to position the match instead.
    """
    provider = ReplayProvider(replay or FOOTBALL, speed=speed, start_minute=start_minute)
    provider.jump_to(start_minute)
    return Context(provider, MemoryStore(), language)
