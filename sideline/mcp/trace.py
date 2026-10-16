"""What one tool call did behind the scenes: the feed it asked, what it changed about the listener.

The tool runner (sideline/app.py) records it as the call finishes; the server (sideline/mcp/server.py) takes it to write the
console log and to attach it to the MCP result as `_meta.sideline`, where a client such as the simulator's Dev log can show it.
Thread-local, because every request runs on its own thread.
"""

import threading

_TL = threading.local()


def record(**fields):
    _TL.rec = dict(fields)


def take():
    rec = getattr(_TL, "rec", None)
    _TL.rec = None
    return rec or {}
