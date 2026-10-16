"""Starting the server twice says so in plain words, with how to fix it, and not with a traceback."""

import errno
import os
import socket
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["SIDELINE_STATE"] = "memory"

from sideline import app      # noqa: E402
from sideline.config import CONFIG   # noqa: E402


def main():
    # Something else holds the port: a program that is not ours.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]
    old = CONFIG.port
    try:
        CONFIG.port = port
    except Exception:                                    # noqa: BLE001  (a frozen config)
        object.__setattr__(CONFIG, "port", port)
    try:
        msg = app._already_running()
    finally:
        try:
            CONFIG.port = old
        except Exception:                                # noqa: BLE001
            object.__setattr__(CONFIG, "port", old)
        s.close()
    assert "used by another program" in msg and "kill" in msg and "SIDELINE_PORT=%d" % (port + 1) in msg, msg
    print("ok  a taken port is explained, with the command to free it and another port to use")
    src = open(os.path.join(ROOT, "sideline", "app.py")).read()
    assert "errno.EADDRINUSE" in src and "sys.exit(_already_running())" in src
    print("ok  the start-up path turns 'address already in use' into that message")
    print("\nport taken: all good")


if __name__ == "__main__":
    main()
