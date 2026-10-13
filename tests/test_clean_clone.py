"""Does the repository work the way the README says it does?

Written because it once did not: `python -m sideline`, the first thing anyone
types, failed on a fresh clone because every test ran with PYTHONPATH set. These
tests run the documented commands in a clean shell, and check the repository holds
what it claims and nothing it removed.

Sideline has no demo mode: with no football key it refuses to start and says why;
with a key it starts. (The key here is fake and the feed is never called: nothing
in startup talks to it.)
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Blank secrets beat a developer's own .env, so this test never uses real keys.
BLANK = {"SIDELINE_FOOTBALL_KEY": "", "GROQ_API_KEY": "", "AWS_ACCESS_KEY_ID": "",
         "AWS_SECRET_ACCESS_KEY": "", "AWS_PROFILE": "", "AWS_BEARER_TOKEN_BEDROCK": "",
         "SIDELINE_BEDROCK": "off", "SIDELINE_STATE": "memory"}


def _clean_env(**extra):
    """A shell with no PYTHONPATH, like a fresh clone."""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.update(BLANK)
    env.update(extra)
    return env


def _start(port, cwd=ROOT, **extra):
    return subprocess.Popen([sys.executable, "-m", "sideline"], cwd=cwd,
                            env=_clean_env(SIDELINE_PORT=str(port), **extra),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def _get(port, path):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=1) as r:
        return r.status, r.read().decode()


def _wait_for_health(proc, port):
    for _ in range(50):
        if proc.poll() is not None:
            raise AssertionError("server exited:\n" + proc.stdout.read())
        try:
            return json.loads(_get(port, "/health")[1])
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.1)
    raise AssertionError("server never answered /health")


def _stop(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def main():
    # ------------------------------------ the package imports with nothing set
    r = subprocess.run([sys.executable, "-c", "import sideline; print(sideline.__version__)"],
                       cwd=ROOT, env=_clean_env(), capture_output=True, text=True)
    assert r.returncode == 0, "import sideline failed:\n" + r.stderr
    print("ok  `import sideline` works with no PYTHONPATH:", r.stdout.strip())

    # ------------------------- no key: a clear refusal, not a traceback, not a demo
    r = subprocess.run([sys.executable, "-m", "sideline"], cwd=ROOT, env=_clean_env(),
                       capture_output=True, text=True, timeout=20)
    out = r.stdout + r.stderr
    assert r.returncode != 0, "the server must not start without a football key"
    assert "SIDELINE_FOOTBALL_KEY is not set" in out and "no recorded" in out, out
    assert "Traceback" not in out, "a missing key is a message, not a stack trace:\n" + out
    print("ok  with no football key it refuses to start and says exactly what to do")

    # ----------------------------------------------------- with a key: it serves
    proc = _start(8799, SIDELINE_FOOTBALL_KEY="not-a-real-key")
    try:
        health = _wait_for_health(proc, 8799)
        assert health["protocol"] == "2025-11-25" and health["tools"] == 9, health
        assert "mode" not in health, "there is no demo/live mode any more"
        status, page = _get(8799, "/")
        assert status == 200 and "Sideline" in page
        for gone in ("preview", "LIVE_MODE", "local routing"):
            assert gone not in page, "%r was removed from the page" % gone
        req = urllib.request.Request(
            "http://127.0.0.1:8799/mcp",
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode(),
            {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            assert len(json.loads(resp.read())["result"]["tools"]) == 9
        print("ok  with a key `python -m sideline` serves on a clean shell:",
              "%d tools, spec %s, the simulator page, MCP tools/list" % (
                  health["tools"], health["protocol"]))
    finally:
        _stop(proc)

    # --------------------- no runtime third-party imports at module scope
    # boto3 is imported behind guards. If an unguarded import creeps in, a reviewer
    # without it gets a traceback instead of a working server.
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
         "import sideline.state, sideline.providers, sideline.sync, sideline.voice\n"
         "print('ok')"],
        cwd=ROOT, env=_clean_env(), capture_output=True, text=True)
    assert r.returncode == 0, "the package needs boto3 to import:\n" + r.stderr
    print("ok  the whole package imports with boto3 unavailable")

    # ----------------------------- the repository holds what it claims, and no more
    for rel in ("README.md", "LICENSE", "Makefile", "requirements.txt", ".env.example",
                "scripts/verify_data.py", "scripts/verify_aws.py", "scripts/create_table.py",
                "simulator/index.html", "docs/ENVIRONMENT.md", "docs/AWS_SETUP.md"):
        assert os.path.exists(os.path.join(ROOT, rel)), "missing: " + rel
    removed = ("data", "deploy", "Dockerfile", "run.py", "sideline/providers/replay.py",
               "sideline/providers/statsbomb.py", "sideline/summaries.py", "sideline/auth.py",
               "sideline/metrics.py", "sideline/secretsmanager.py", "sideline/autodetect.py",
               "scripts/lambda_handler.py", "scripts/smoke_test.py")
    for rel in removed:
        assert not os.path.exists(os.path.join(ROOT, rel)), "was removed on purpose: " + rel
    print("ok  every file the docs point at is present, and nothing that was removed has come back")

    # the product ships no recorded data: invented test fixtures live in tests/ only
    for dirpath, _, files in os.walk(os.path.join(ROOT, "sideline")):
        assert not [f for f in files if f.endswith(".json")], \
            "recorded data in the product: %s %s" % (dirpath, files)
    print("ok  no data files anywhere in the product package")

    # a virtualenv must never be committed
    try:
        tracked = subprocess.run(["git", "ls-files", ".venv", "venv"], cwd=ROOT,
                                 capture_output=True, text=True, timeout=10).stdout.split()
    except (OSError, subprocess.SubprocessError):
        tracked = []
    assert not tracked, "a virtualenv is tracked in git (%d files)" % len(tracked)
    print("ok  no virtualenv is tracked in git")

    print("\nclean clone: all good")


if __name__ == "__main__":
    main()
