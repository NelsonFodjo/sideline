"""Lambda entry point for the poller.

EventBridge Scheduler invokes this every 15 seconds. It is three lines
around poll_once() on purpose: the poller has no idea whether a thread
or a scheduler is calling it, which is why the same code runs locally
and in production.

See docs/DEPLOYMENT.md for the schedule definition.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sideline.app import build  # noqa: E402
from sideline.poller import poll_once  # noqa: E402

_ctx = None


def handler(event, context):
    global _ctx
    if _ctx is None:
        _ctx, _, _ = build()      # reused across warm invocations
    found = poll_once(_ctx)
    return {"logged": found}
