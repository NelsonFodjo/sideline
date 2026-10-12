import os
import sys

# The package sits at the repo root, so `python -m sideline` works from
# a clean clone with no install step and no PYTHONPATH. Tests only
# need the root on the path.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sideline import language                       # noqa: E402
from sideline.app import Context                    # noqa: E402
from sideline.providers.replay import ReplayProvider  # noqa: E402
from sideline.state import MemoryStore              # noqa: E402

REPLAY = os.path.join(os.path.dirname(__file__), "..",
                      "data", "replay", "arsenal-spurs.json")


def make_ctx(start_minute=0, speed=10000.0):
    """Context wired to the replay harness.

    speed is enormous by default so tests do not wait on a clock; they
    call provider.jump_to() to position the match instead.
    """
    provider = ReplayProvider(REPLAY, speed=speed, start_minute=start_minute)
    provider.jump_to(start_minute)
    return Context(provider, MemoryStore(), language)
