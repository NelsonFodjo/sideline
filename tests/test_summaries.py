"""Precomputed summaries: the model is off the listener's clock.

The model is replaced by a fake that takes 300 ms, so the tests show the
mechanism rather than any real Bedrock latency (none has been measured).
"""

import threading
import time

from conftest import make_ctx

from sideline import summaries
from sideline.language import bedrock
from sideline.poller import poll_once
from sideline.tools import REGISTRY

TEXT = "Arsenal went ahead and Tottenham answered; that is where it stands."
CALLS = []
GATE = threading.Event()
GATE.set()
REPLY = [TEXT]


def fake_converse(system, user_text, max_tokens=160):
    if not bedrock.ENABLED:          # the real _converse returns None when off
        return None
    CALLS.append(time.time())
    time.sleep(0.3)                  # a slow model
    GATE.wait(5)
    return REPLY[0]


def wait_until(fn, timeout=4.0):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.02)
    return False


def ask(ctx, who):
    t0 = time.perf_counter()
    spoken, s, _ = REGISTRY["what_did_i_miss"](ctx, {}, who)
    return spoken, s, (time.perf_counter() - t0) * 1000


def idle():
    return wait_until(lambda: not summaries._inflight)


def main():
    saved = (bedrock._converse, bedrock.ENABLED, bedrock.HAVE_BOTO3, summaries.MODE)
    bedrock._converse, bedrock.ENABLED, bedrock.HAVE_BOTO3 = fake_converse, True, True
    try:
        summaries.MODE = "cached"
        summaries.CACHE.clear()
        ctx = make_ctx(start_minute=0, speed=0.0001)     # frozen clock: jump_to() moves it
        fid = REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "L1")[1]["fixture_id"]

        # --- a poll that logs events precomputes the summary in the background
        ctx.provider.jump_to(40)
        t0 = time.perf_counter()
        poll_once(ctx)
        poll_ms = (time.perf_counter() - t0) * 1000
        assert poll_ms < 250, "the poller must not wait on the model: %.0f ms" % poll_ms
        assert wait_until(lambda: len(summaries.CACHE) >= 1), "nothing was precomputed"
        calls = len(CALLS)
        print("ok  poll returned in %.0f ms; the 300 ms model ran in the background" % poll_ms)

        # --- asking is a cache hit: instant, no model call
        spoken, s, ms = ask(ctx, "L1")
        assert s["summary_source"] == "precomputed" and s["generated_by"] == "bedrock", s
        assert spoken == TEXT and len(CALLS) == calls
        assert ms < 100, ms
        print("ok  ask = cache hit in %.1f ms with no model call (model takes 300 ms)" % ms)

        # --- a second listener with the same window shares the one generation
        REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "L2")
        spoken2, s2, _ = ask(ctx, "L2")
        assert s2["summary_source"] == "precomputed" and len(CALLS) == calls
        print("ok  a second listener with the same window shares it (still %d model call)" % calls)

        # --- never stale, never waits: new events -> miss -> template at once
        GATE.clear()                                    # hold the model
        ctx.provider.jump_to(80)
        poll_once(ctx)
        REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "L3")
        spoken3, s3, ms3 = ask(ctx, "L3")
        assert s3["summary_source"] == "template-fast" and s3["generated_by"] == "template", s3
        assert ms3 < 100 and spoken3 != TEXT
        print("ok  new events with the model busy: answered by template in %.1f ms, never stale" % ms3)
        GATE.set()
        assert idle()

        # --- the next ask in the new state is a hit
        REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "L4")
        summaries.schedule(ctx, fid)
        assert idle()
        spoken4, s4, _ = ask(ctx, "L4")
        assert s4["summary_source"] == "precomputed" and spoken4 == TEXT
        print("ok  once generated, the same state is a hit")

        # --- a scoreline that disagrees with ours is never cached
        summaries.CACHE.clear()
        REPLY[0] = "Arsenal lead 9-9 after a wild first half."
        REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "L5")
        summaries.schedule(ctx, fid)
        assert idle()
        assert len(summaries.CACHE) == 0, "an ungrounded summary was cached"
        spoken5, s5, _ = ask(ctx, "L5")
        assert s5["summary_source"] == "template-fast" and "9-9" not in spoken5
        print("ok  a contradicting scoreline is discarded, not cached; the template answers")
        REPLY[0] = TEXT

        # --- live mode is the old behaviour: the model is called at ask time
        summaries.MODE = "live"
        summaries.CACHE.clear()
        REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "L6")
        before = len(CALLS)
        spoken6, s6, ms6 = ask(ctx, "L6")
        assert s6["summary_source"] == "live" and len(CALLS) == before + 1 and ms6 >= 250
        print("ok  SIDELINE_CATCHUP_MODE=live calls the model at ask time (%.0f ms)" % ms6)

        # --- non-English listeners are not answered in English from the template
        summaries.MODE = "cached"
        l = ctx.store.listener("L7")
        l["language"] = "fr"
        l["following"] = fid
        ctx.store.save_listener(l)
        before = len(summaries.CACHE)
        summaries.schedule(ctx, fid)
        idle()
        spoken7, s7, _ = ask(ctx, "L7")
        assert s7["summary_source"] == "live" and "+" in s7["generated_by"], s7
        print("ok  a French listener takes the live path (translated), not the English template")

        # --- no model configured: plain template, nothing queued
        bedrock.ENABLED = False
        REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "L8")
        n = len(CALLS)
        _, s8, _ = ask(ctx, "L8")
        assert s8["summary_source"] == "template" and len(CALLS) == n
        assert summaries.schedule(ctx, fid) == 0
        print("ok  with Bedrock off nothing is queued and the template answers")
        bedrock.ENABLED = True

        # --- the cache is bounded
        c = summaries.Cache(max_entries=3)
        for i in range(6):
            c.put("k%d" % i, "t", "bedrock")
            time.sleep(0.002)
        assert len(c) == 3 and c.get("k5") and not c.get("k0")
        print("ok  the cache is bounded and evicts the oldest")

        # --- the Dynamo store can say who follows a fixture, with a fake table
        try:
            from boto3.dynamodb.conditions import Key  # noqa: F401
        except ImportError:
            print("skip  DynamoDB followers (boto3 not installed)")
        else:
            from sideline.state.dynamo import DynamoStore
            from sideline.state.store import Listener

            class FakeTable:
                def __init__(self):
                    self.items = []

                def put_item(self, Item, **kw):
                    self.items.append(Item)

                def get_item(self, Key):
                    for i in reversed(self.items):
                        if i["PK"] == Key["PK"] and i["SK"] == Key["SK"]:
                            return {"Item": i}
                    return {}

                def query(self, KeyConditionExpression):
                    cond = KeyConditionExpression.get_expression()
                    pk = cond["values"][0].get_expression()["values"][1]
                    return {"Items": [i for i in self.items if i["PK"] == pk]}

            d = DynamoStore.__new__(DynamoStore)
            d._t = FakeTable()
            for lid, fx in (("a", "F1"), ("b", "F1"), ("c", "F2")):
                rec = Listener.make(lid)
                rec["following"] = fx
                d.save_listener(rec)
            assert d.followers("F1") == ["a", "b"] and d.followers("F2") == ["c"]
            moved = Listener.make("a")
            moved["following"] = "F2"
            d.save_listener(moved)
            assert d.followers("F1") == ["b"], "a stale marker was not filtered"
            print("ok  DynamoDB followers: marker items, stale ones filtered (fake table; real DynamoDB not run)")
    finally:
        bedrock._converse, bedrock.ENABLED, bedrock.HAVE_BOTO3, summaries.MODE = saved
        GATE.set()

    print("\nsummaries: all good")


if __name__ == "__main__":
    main()
