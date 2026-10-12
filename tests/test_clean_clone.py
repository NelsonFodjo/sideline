"""Does the repository work the way the README says it does?

This suite exists because it did not. The package sat under src/, every
test ran with PYTHONPATH set, and `python -m sideline` - the first line
of the README and the first thing anyone types - failed with
"No module named sideline".

Nobody caught it because nobody ever ran the documented command in a
clean shell. These tests do.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _clean_env():
    """A shell with no PYTHONPATH, like a fresh clone."""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return env


def main():
    # -----------------------------------------------------------
    # The package imports from the repo root with nothing set
    # -----------------------------------------------------------
    r = subprocess.run([sys.executable, "-c", "import sideline; print(sideline.__version__)"],
                       cwd=ROOT, env=_clean_env(), capture_output=True, text=True)
    assert r.returncode == 0, "import sideline failed:\n" + r.stderr
    print("ok  `import sideline` works with no PYTHONPATH:", r.stdout.strip())

    # -----------------------------------------------------------
    # The documented command actually serves
    # -----------------------------------------------------------
    # Not "does the module resolve" - start it and talk to it. The first
    # version of this test ran `python -m sideline --help`, which simply
    # started the server and blocked until the timeout, because there is
    # no argument parsing. A test that cannot fail for the right reason
    # is worse than no test.
    import json
    import time
    import urllib.error
    import urllib.request

    env = _clean_env()
    env["SIDELINE_PORT"] = "8799"
    proc = subprocess.Popen([sys.executable, "-m", "sideline"], cwd=ROOT,
                            env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        health = None
        for _ in range(40):                       # up to 4 seconds
            if proc.poll() is not None:
                raise AssertionError("server exited:\n" + proc.stdout.read())
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:8799/health", timeout=1) as r:
                    health = json.loads(r.read().decode())
                break
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                time.sleep(0.1)
        assert health, "server never answered /health"
        assert health["protocol"] == "2025-11-25", health
        assert health["tools"] == 9, health
        print("ok  `python -m sideline` serves on a clean shell:",
              "%d tools, spec %s" % (health["tools"], health["protocol"]))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    # -----------------------------------------------------------
    # No runtime third-party imports at module scope
    # -----------------------------------------------------------
    # boto3 is imported, but every site is guarded. If an unguarded
    # third-party import creeps in, a reviewer with nothing installed
    # gets a traceback instead of a working server - and during the
    # judging window that scores zero.
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys\n"
         "class Block:\n"
         "    def find_module(self, name, path=None):\n"
         "        return self if name.split('.')[0] in ('boto3','botocore') else None\n"
         "    def load_module(self, name):\n"
         "        raise ImportError('blocked for this test')\n"
         "sys.meta_path.insert(0, Block())\n"
         "import sideline.app, sideline.tools, sideline.language.bedrock\n"
         "import sideline.state, sideline.providers, sideline.sync\n"
         "print('ok')"],
        cwd=ROOT, env=_clean_env(), capture_output=True, text=True)
    assert r.returncode == 0, "the package needs boto3 to import:\n" + r.stderr
    print("ok  whole package imports with boto3 unavailable")

    # -----------------------------------------------------------
    # Every path the README tells someone to type exists
    # -----------------------------------------------------------
    for rel in ("README.md", "LICENSE", "Makefile", "requirements.txt",
                "data/replay/arsenal-spurs.json", "scripts/smoke_test.py",
                "scripts/verify_aws.py", "simulator/index.html",
                "docs/AWS_SETUP.md", "docs/COMPLIANCE.md"):
        assert os.path.exists(os.path.join(ROOT, rel)), "missing: " + rel
    print("ok  every file the docs point at is present")

    # -----------------------------------------------------------
    # run.py works too, and fails usefully from the wrong directory
    # -----------------------------------------------------------
    # Invoked from somewhere else entirely. This caught a second bug:
    # the replay data path was relative to the working directory, so the
    # server started and then died looking for a file - an error that
    # has nothing to do with what the user did wrong.
    env = _clean_env()
    env["SIDELINE_PORT"] = "8798"
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "run.py")],
                            cwd="/tmp", env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        ok = False
        for _ in range(40):
            if proc.poll() is not None:
                raise AssertionError("run.py from /tmp exited:\n"
                                     + proc.stdout.read())
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:8798/health", timeout=1) as r:
                    r.read()
                ok = True
                break
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                time.sleep(0.1)
        assert ok, "run.py did not serve when invoked from another directory"
        print("ok  run.py works from any working directory")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    print("\nclean clone: all good")


if __name__ == "__main__":
    main()
