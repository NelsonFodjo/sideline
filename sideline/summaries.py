"""Precomputed catch-up summaries for non-strict mode.

In live mode, every catch-up request calls Bedrock and failures propagate.
The cache and template-on-miss behavior below are only used outside strict
live mode.

In cached mode, the poller can precompute per-listener summaries in a
background thread. A cache hit uses model-generated text; a miss uses a
template and queues generation. Strict live mode bypasses both behaviors.
"""

import logging
import os
import threading
import time

from . import autodetect

LOG = logging.getLogger("sideline.summaries")
MODE = autodetect.catchup_mode(os.environ)
MAX_ENTRIES = 256
MAX_PARALLEL = 2


class Cache:
    def __init__(self, max_entries=MAX_ENTRIES):
        self._d = {}
        self._max = max_entries
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            hit = self._d.get(key)
            return (hit[0], hit[1]) if hit else None

    def put(self, key, text, how):
        with self._lock:
            self._d[key] = (text, how, time.time())
            while len(self._d) > self._max:
                oldest = min(self._d, key=lambda k: self._d[k][2])
                del self._d[oldest]

    def __len__(self):
        with self._lock:
            return len(self._d)

    def clear(self):
        with self._lock:
            self._d.clear()


CACHE = Cache()
_inflight = set()
_inflight_lock = threading.Lock()
_slots = threading.BoundedSemaphore(MAX_PARALLEL)


def window_key(fx, mode, events, language):
    ids = ",".join("%s%s" % (e["id"], "!" if e.get("superseded_by") else "")
                   for e in events)
    sc = fx.get("score") or {}
    return "%s|%s|%s|%s-%s|%s" % (fx.get("fixture_id"), mode, language or "en",
                                  sc.get("home"), sc.get("away"), ids)


def plan(events, fx, frm, to, away_limit_args=None):
    """(mode, away) for a window, using the same rule as the tool."""
    from .tools.what_did_i_miss import LONG_ABSENCE_MINUTES
    now = fx.get("minute") or to
    away = max(0, now - frm)
    long_absence = away > LONG_ABSENCE_MINUTES and len(events) > 3
    return ("milestones" if long_absence else "full"), away


def _generate(bedrock, mode, events, fx, frm, to, away):
    if mode == "milestones":
        return bedrock.milestones(events, fx, away)
    return bedrock.catchup(events, fx, frm, to)


def _run_job(bedrock, key, mode, events, fx, frm, to, away):
    try:
        with _slots:
            text, how = _generate(bedrock, mode, events, fx, frm, to, away)
        if how == "bedrock":                 # only guard-approved model text
            CACHE.put(key, text, how)
            LOG.info("summary cached (%s, %d events)", mode, len(events))
        else:
            LOG.info("summary not cached: came back as %s", how)
    except Exception as e:                                     # noqa: BLE001
        LOG.warning("summary generation failed: %s", e)
    finally:
        with _inflight_lock:
            _inflight.discard(key)


def _queue(bedrock, key, mode, events, fx, frm, to, away):
    with _inflight_lock:
        if key in _inflight or CACHE.get(key):
            return False
        _inflight.add(key)
    threading.Thread(target=_run_job, daemon=True, name="sideline-summary",
                     args=(bedrock, key, mode, list(events), dict(fx), frm, to, away)).start()
    return True


def enabled(ctx):
    return (MODE == "cached" and not ctx.lang.bedrock.STRICT_LIVE
            and ctx.lang.bedrock.available())


def schedule(ctx, fixture_id):
    """Precompute for every follower of a fixture. Never raises, never blocks."""
    if not enabled(ctx):
        return 0
    from .mcp.errors import ToolError
    from .tools import resolve_fixture
    queued = 0
    try:
        for lid in ctx.store.followers(fixture_id):
            try:
                fx = resolve_fixture(ctx, {}, lid)
                events, frm, to = ctx.store.gap_for(lid, fixture_id)
            except ToolError:
                continue
            if not events:
                continue
            language = ctx.store.listener(lid).get("language")
            if language not in (None, "", "en"):
                continue                      # non-English takes the live path
            mode, away = plan(events, fx, frm, to)
            key = window_key(fx, mode, events, language)
            if _queue(ctx.lang.bedrock, key, mode, events, fx, frm, to, away):
                queued += 1
    except Exception as e:                                     # noqa: BLE001
        LOG.warning("precompute failed: %s", e)
    return queued


def answer(ctx, mode, events, fx, frm, to, away, language):
    """The words for a catch-up, and where they came from.

    Returns (spoken, generated_by, summary_source).
    """
    bedrock = ctx.lang.bedrock
    english = language in (None, "", "en")

    def live():
        text, how = _generate(bedrock, mode, events, fx, frm, to, away)
        if not english:
            text, how2 = bedrock.translate(text, language)
            how = "%s+%s" % (how, how2)
        return text, how

    if not bedrock.available() or not events:
        text, how = live()
        return text, how, "template"
    if bedrock.STRICT_LIVE or MODE != "cached" or not english:
        text, how = live()
        return text, how, "live"

    key = window_key(fx, mode, events, language)
    hit = CACHE.get(key)
    if hit:
        return hit[0], hit[1], "precomputed"

    # A miss must not wait on the model. Answer now with the template and
    # have the model write it for next time.
    _queue(bedrock, key, mode, events, fx, frm, to, away)
    if mode == "milestones":
        text = bedrock.template_milestones(events, fx, away)
    else:
        text = bedrock.template_catchup(events, fx, frm, to)
    return text, "template", "template-fast"
