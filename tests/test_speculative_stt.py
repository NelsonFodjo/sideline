"""The page starts transcribing during the quiet after speech, and never starts the agent on a guess.

A static check of simulator/index.html (the page has no browser test here): the speculative request asks for text only,
it is dropped if the listener carries on, and only a committed transcript reaches ask().
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def body(src, name):
    start = src.index("function %s(" % name)
    depth, i = 0, src.index("{", start)
    for j in range(i, len(src)):
        depth += {"{": 1, "}": -1}.get(src[j], 0)
        if depth == 0:
            return src[start:j + 1]


def main():
    src = open(os.path.join(ROOT, "simulator", "index.html"), encoding="utf-8").read()
    spec = body(src, "startSpec")
    assert "/voice/stt" in spec and "X-Run-Agent" not in spec, "the speculative request is transcription only"
    commit = body(src, "commitSpec")
    assert "ask(" in commit and "endCapture()" in commit
    assert "ask(" not in body(src, "startSpec") and "ask(" not in body(src, "peekCapture")
    quiet = int(re.search(r"var SPEC_QUIET_MS=(\d+)", src).group(1))
    full = [int(n) for n in re.search(r"var silenceLimit=\(words>=4\)\?(\d+):\(words>=2\)\?(\d+):(\d+)", src).groups()]
    assert 200 <= quiet < min(full), (quiet, full)
    listen = body(src, "listen")
    assert "spec.ctl.abort()" in listen and "quietFor<SPEC_QUIET_MS" in listen, "carrying on drops the speculative result"
    assert "handleClip(endCapture(), snapCap2)" in listen, "a failed speculative request falls back to the normal path"
    print("ok  speculative transcription starts after %d ms of quiet (full limit %d to %d ms), is text-only, and is dropped if the "
          "listener carries on" % (quiet, min(full), max(full)))
    print("\nspeculative stt: all good")


if __name__ == "__main__":
    main()
