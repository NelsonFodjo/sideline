"""DynamoDB backend.

Durable listener state and the match event log. Enable with
SIDELINE_STATE=dynamo (or leave it on auto: it is used when AWS credentials are
present and the table answers; create it with `make create-table`).
Verified on a real table: see docs/AWS_SETUP.md.

The semantics are identical to MemoryStore, and the gap calculation
lives on the shared base class precisely so the two backends cannot
drift apart.

Table design (single table, because the access patterns are few and
known):

    PK                      SK                  attributes
    LISTENER#<id>           PROFILE             following, supports,
                                                last_told_at, told_event_ids
    FIXTURE#<id>            EVENT#<minute>#<id> kind, player, detail, ...
    FIXTURE#<id>            META                teams, kickoff, status

Why single-table: the two hot reads are "give me this listener" and
"give me every event for this fixture in minute order". Both are a
single query. Nothing here needs a scan, and nothing needs a GSI.

Capacity: on-demand. A followed match writes single-digit items a minute;
provisioning for that is a waste.

TTL: set `expires_at` on event items to 48 hours after kickoff. Match
events have no value afterwards and keeping them costs money and
creates a privacy surface for no reason.
"""

import copy
import hashlib
import logging
import threading
import time
from decimal import Decimal

from .store import Event, Listener, Store

LOG = logging.getLogger("sideline.dynamo")

# A turn reads the listener and the match several times, and each DynamoDB call is a network round trip (about 340 ms from
# Mauritius to us-east-1). These are the server's OWN records (listeners, the event log it wrote, the match snapshots it
# saved), not the live feed: every write made through this store replaces or drops what it touches, so one server always
# sees its own writes at once. Another instance's write can take this long to show, which is why one server per table is
# the supported shape (README, "Look after it"). Live match data is never kept here; it comes from the feed.
LISTENER_READ_SECONDS = 60.0
FIXTURE_READ_SECONDS = 60.0
EVENTS_READ_SECONDS = 60.0
FOLLOWERS_READ_SECONDS = 30.0

try:
    import boto3
    from boto3.dynamodb.conditions import Key
    HAVE_BOTO3 = True
except ImportError:                                            # pragma: no cover
    boto3 = None
    Key = None
    HAVE_BOTO3 = False


def to_ddb(obj):
    """Python -> DynamoDB. The service rejects floats; use Decimal.

    Found by running against a real table: every event carries a float
    timestamp, so without this the poller could not log a single event.
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: to_ddb(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_ddb(v) for v in obj]
    return obj


def from_ddb(obj):
    """DynamoDB -> Python. Numbers come back as Decimal, which JSON cannot
    encode and `%d` formatting trips over; give back int or float."""
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, dict):
        return {k: from_ddb(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [from_ddb(v) for v in obj]
    return obj


def event_sk(event):
    """Sort key for an event: minute order, then a digest of what makes two
    events the same one.

    The digest is (kind, player), the same identity MemoryStore uses within a
    minute. It must NOT include the event id: live providers mint a new id on
    every read, so an id in the key makes the dedupe condition never fire and
    every poll re-writes every event.
    """
    from .store import event_key
    ident = "|".join(str(p) for p in event_key(event)[1:])        # the minute is already in the key
    return "EVENT#%03d#%s" % (int(event["minute"]),
                              hashlib.sha1(ident.encode("utf-8")).hexdigest()[:12])


class DynamoStore(Store):
    def __init__(self, table_name, region="us-east-1"):
        if not HAVE_BOTO3:
            raise RuntimeError(
                "SIDELINE_STATE=dynamo needs boto3. pip install boto3, or "
                "leave SIDELINE_STATE=memory to run with no dependencies.")
        self.table_name = table_name
        self.region = region
        self._t = boto3.resource("dynamodb", region_name=region).Table(table_name)
        self._init_cache()

    _SETUP = threading.Lock()

    def _init_cache(self):
        self._kept = {}
        self._kept_lock = threading.Lock()

    def _cache(self):
        """The kept reads and their lock, made on first use (a store built without __init__, as tests do, works too)."""
        if "_kept_lock" not in self.__dict__:
            with DynamoStore._SETUP:
                if "_kept_lock" not in self.__dict__:
                    self._init_cache()
        return self._kept, self._kept_lock

    def _together(self, *calls):
        """Run independent DynamoDB calls at the same time: N round trips cost one."""
        calls = [c for c in calls if c]
        if len(calls) < 2:
            for c in calls:
                c()
            return
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            for f in [pool.submit(c) for c in calls]:
                f.result()

    def _keep_drop_prefix(self, prefix):
        kept, lock = self._cache()
        with lock:
            for k in [k for k in kept if k[0] == prefix]:
                kept.pop(k, None)

    def _keep_get(self, key, ttl):
        kept, lock = self._cache()
        with lock:
            hit = kept.get(key)
            if hit and time.monotonic() - hit[0] <= ttl:
                return True, copy.deepcopy(hit[1])
        return False, None

    def _keep_set(self, key, value):
        kept, lock = self._cache()
        with lock:
            kept[key] = (time.monotonic(), copy.deepcopy(value))

    def _keep_drop(self, key):
        kept, lock = self._cache()
        with lock:
            kept.pop(key, None)

    # ------------------------------------------------------------ reads
    def listener(self, listener_id):
        found, rec = self._keep_get(("listener", listener_id), LISTENER_READ_SECONDS)
        if found:
            return Listener(rec)
        r = self._t.get_item(
            Key={"PK": "LISTENER#" + listener_id, "SK": "PROFILE"}).get("Item")
        rec = Listener(from_ddb(r["data"])) if r else Listener.make(listener_id)
        self._keep_set(("listener", listener_id), rec)
        return rec

    def events(self, fixture_id):
        found, kept = self._keep_get(("events", str(fixture_id)), EVENTS_READ_SECONDS)
        if found:
            return [Event(e) for e in kept]
        # Query, not scan. The sort-key prefix keeps them in minute order
        # for free, which is exactly what gap_for() wants.
        r = self._t.query(
            KeyConditionExpression=Key("PK").eq("FIXTURE#%s" % fixture_id)
                                   & Key("SK").begins_with("EVENT#"))
        out = [Event(from_ddb(i["data"])) for i in r.get("Items", [])]
        # Same order as MemoryStore: minute, then when we logged it.
        out.sort(key=lambda e: (e["minute"], e.get("at") or 0))
        self._keep_set(("events", str(fixture_id)), out)
        return out

    def fixture(self, fixture_id):
        found, rec = self._keep_get(("fixture", str(fixture_id)), FIXTURE_READ_SECONDS)
        if found:
            return rec
        r = self._t.get_item(
            Key={"PK": "FIXTURE#%s" % fixture_id, "SK": "META"}).get("Item")
        rec = from_ddb(r["data"]) if r else None
        self._keep_set(("fixture", str(fixture_id)), rec)
        return rec

    def followers(self, fixture_id):
        found, kept = self._keep_get(("followers", str(fixture_id)), FOLLOWERS_READ_SECONDS)
        if found:
            return kept
        r = self._t.query(
            KeyConditionExpression=Key("PK").eq("FOLLOWERS#%s" % fixture_id)
                                   & Key("SK").begins_with("LISTENER#"))
        ids = [i["SK"][len("LISTENER#"):] for i in r.get("Items", [])]
        # Drop markers left by listeners who have since followed another match.
        if len(ids) > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(8, len(ids))) as pool:        # one profile read each, together
                current = list(pool.map(lambda i: self.listener(i).get("following") == fixture_id, ids))
        else:
            current = [self.listener(i).get("following") == fixture_id for i in ids]
        out = sorted(i for i, ok in zip(ids, current) if ok)
        self._keep_set(("followers", str(fixture_id)), out)
        return out

    def all_followed_fixtures(self):
        """Fixtures at least one listener is following right now: what the poller polls.

        INDEX#FOLLOWED lists every fixture ever saved, so each is checked against its followers
        (the same marker-then-profile check `followers` does). Without that, every match anyone ever
        followed would be polled for ever, against a feed that allows a few hundred calls an hour.
        The set is small and bounded by how many matches one server has seen, and it needs no scan.
        """
        found, indexed = self._keep_get(("index", "followed"), FIXTURE_READ_SECONDS)
        if not found:
            r = self._t.query(
                KeyConditionExpression=Key("PK").eq("INDEX#FOLLOWED")
                                       & Key("SK").begins_with("FIXTURE#"))
            indexed = sorted({from_ddb(i["data"])["fixture_id"] for i in r.get("Items", [])})
            self._keep_set(("index", "followed"), indexed)
        if len(indexed) < 2:
            return sorted(f for f in indexed if self.followers(f))
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(8, len(indexed))) as pool:         # one check per match, together
            has = list(pool.map(lambda f: bool(self.followers(f)), indexed))
        return sorted(f for f, h in zip(indexed, has) if h)

    # ----------------------------------------------------------- writes
    def save_listener(self, rec):
        profile = lambda: self._t.put_item(Item={"PK": "LISTENER#" + rec["listener_id"],
                                                 "SK": "PROFILE", "data": to_ddb(rec)})
        # A marker so "who follows this fixture" is a Query, not a scan. Stale markers (a listener who switched match)
        # expire with the TTL and are filtered on read.
        marker = (lambda: self._t.put_item(Item={
            "PK": "FOLLOWERS#%s" % rec["following"],
            "SK": "LISTENER#%s" % rec["listener_id"],
            "expires_at": int(time.time()) + 48 * 3600})) if rec.get("following") else None
        self._together(profile, marker)
        self._keep_drop_prefix("followers")
        # Last-write-wins is correct here: a listener is one person with
        # one voice. Concurrent writes to the same profile do not happen,
        # and a conditional write would buy nothing but latency.
        self._keep_set(("listener", rec["listener_id"]), rec)
        return rec

    def forget_listener(self, listener_id):
        rec = self.listener(listener_id)
        following = rec.get("following")
        self._together(
            lambda: self._t.delete_item(Key={"PK": "LISTENER#" + listener_id, "SK": "PROFILE"}),
            (lambda: self._t.delete_item(Key={"PK": "FOLLOWERS#%s" % following, "SK": "LISTENER#" + listener_id}))
            if following else None)
        self._keep_drop(("listener", listener_id))
        self._keep_drop_prefix("followers")

    def append_events(self, events):
        """A match's events written together: each is a conditional write and a network round trip (about 340 ms from
        Mauritius), so twenty one after another was seven seconds on the first follow. Eight at a time is under one."""
        events = list(events)
        if len(events) < 2:
            return Store.append_events(self, events)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(8, len(events))) as pool:
            list(pool.map(self.append_event, events))

    def append_event(self, event):
        # The one place a condition expression genuinely earns its keep.
        # The poller re-reads an overlapping window every cycle; without
        # this the listener is told about the same goal on every poll.
        try:
            self._t.put_item(
                Item={"PK": "FIXTURE#%s" % event["fixture_id"],
                      "SK": event_sk(event),
                      # Match events have no value after the match. TTL
                      # saves money and removes a privacy surface.
                      "expires_at": int(time.time()) + 48 * 3600,
                      "data": to_ddb(event)},
                ConditionExpression="attribute_not_exists(PK)")
        except self._t.meta.client.exceptions.ConditionalCheckFailedException:
            pass
        self._keep_drop(("events", str(event["fixture_id"])))
        return event

    def supersede(self, fixture_id, event_id, by_event_id):
        for e in self.events(fixture_id):
            if e["id"] == event_id:
                e["superseded_by"] = by_event_id
                self._t.put_item(
                    Item={"PK": "FIXTURE#%s" % fixture_id,
                          "SK": event_sk(e),
                          "expires_at": int(time.time()) + 48 * 3600,
                          "data": to_ddb(e)})
                self._keep_drop(("events", str(fixture_id)))
                return e
        return None

    def save_fixture(self, rec):
        self._together(
            lambda: self._t.put_item(Item={"PK": "FIXTURE#%s" % rec["fixture_id"],
                                           "SK": "META", "data": to_ddb(rec)}),
            lambda: self._t.put_item(Item={"PK": "INDEX#FOLLOWED",
                                           "SK": "FIXTURE#%s" % rec["fixture_id"],
                                           "data": {"fixture_id": rec["fixture_id"]}}))
        self._keep_set(("fixture", str(rec["fixture_id"])), rec)
        self._keep_drop(("index", "followed"))
        return rec
