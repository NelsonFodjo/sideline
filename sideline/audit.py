"""A folder of logs, kept for backup and for answering "what happened?" afterwards.

    logs/
      sideline-2026-10-17.log     everything the server logs, one file per day
      calls-2026-10-17.jsonl      one JSON line per tool call, agent turn and speech clip

A new file starts each day (local midnight), and files older than SIDELINE_LOG_KEEP_DAYS are deleted.
`make log-report` summarises the JSON lines: which tools were used, how fast, what was declined.

What is recorded: tool names, their arguments, latency and outcome; what a listener asked and what
Sideline answered; which speech provider heard a clip and what it heard. Never audio. Never a token or
key: any secret from the environment is replaced with *** wherever it would appear. The folder is
local, ignored by git, and `SIDELINE_LOG_DIR=off` turns all of it off.
"""

import datetime
import json
import logging
import os
import re
import threading

_lock = threading.Lock()
_state = {"dir": None, "keep": 14}
_FILES = re.compile(r"^(sideline|calls)-(\d{4}-\d{2}-\d{2})\.(log|jsonl)$")


def _today():
    return datetime.date.today().isoformat()


def _secrets():
    """Every secret value in the environment worth hiding (see config.VARIABLES)."""
    from . import config
    out = []
    for name, secret, *_ in config.VARIABLES:
        value = os.environ.get(name, "")
        if secret and len(value) >= 8:
            out.append(value)
    return out


def redact(value):
    """`value` with every secret replaced by ***; works through dicts and lists."""
    if isinstance(value, str):
        for secret in _secrets():
            value = value.replace(secret, "***")
        return value
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


class _DailyFile(logging.Handler):
    """A log handler that writes to sideline-<date>.log and starts a new file each day."""

    def __init__(self):
        super().__init__()
        self._day, self._fh = None, None

    def emit(self, record):
        try:
            directory = _state["dir"]
            if not directory:
                return
            day = _today()
            if day != self._day:
                if self._fh:
                    self._fh.close()
                self._fh = open(os.path.join(directory, "sideline-%s.log" % day), "a", encoding="utf-8")
                self._day = day
                prune()
            self._fh.write(redact(self.format(record)) + "\n")
            self._fh.flush()
        except Exception:                                           # noqa: BLE001  logging must never break the server
            self.handleError(record)


def setup(directory, keep_days=14):
    """Start writing logs to `directory` (None or "off" does nothing). Returns the folder or None."""
    if not directory or str(directory).strip().lower() in ("off", "none", "0", "false", "no"):
        _state["dir"] = None
        return None
    directory = os.path.abspath(directory)
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as e:
        logging.getLogger("sideline.audit").warning("logs are off: cannot create %s (%s)", directory, e)
        _state["dir"] = None
        return None
    _state["dir"], _state["keep"] = directory, max(1, int(keep_days))
    root = logging.getLogger()
    if not any(isinstance(h, _DailyFile) for h in root.handlers):
        handler = _DailyFile()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(name)s  %(message)s"))
        root.addHandler(handler)
    prune()
    return directory


def prune(today=None):
    """Delete log files older than the retention. Returns the names removed."""
    directory = _state["dir"]
    if not directory:
        return []
    cutoff = (today or datetime.date.today()) - datetime.timedelta(days=_state["keep"])
    removed = []
    for name in os.listdir(directory):
        m = _FILES.match(name)
        if m and datetime.date.fromisoformat(m.group(2)) < cutoff:
            try:
                os.remove(os.path.join(directory, name))
                removed.append(name)
            except OSError:
                pass
    return removed


def record(kind, **fields):
    """Append one JSON line to today's calls file. A no-op when logs are off; never raises."""
    directory = _state["dir"]
    if not directory:
        return
    line = {"time": datetime.datetime.now().astimezone().isoformat(timespec="milliseconds"), "kind": kind}
    line.update(fields)
    try:
        text = json.dumps(redact(line), ensure_ascii=False, default=str)
        with _lock, open(os.path.join(directory, "calls-%s.jsonl" % _today()), "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    except Exception:                                               # noqa: BLE001
        pass
