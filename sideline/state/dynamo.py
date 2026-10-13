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

import hashlib
import logging
from decimal import Decimal

from .store import Event, Listener, Store

LOG = logging.getLogger("sideline.dynamo")

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
    ident = "%s|%s" % (event.get("kind"), event.get("player"))
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

    # ------------------------------------------------------------ reads
    def listener(self, listener_id):
        r = self._t.get_item(
            Key={"PK": "LISTENER#" + listener_id, "SK": "PROFILE"}).get("Item")
        if not r:
            return Listener.make(listener_id)
        return Listener(from_ddb(r["data"]))

    def events(self, fixture_id):
        # Query, not scan. The sort-key prefix keeps them in minute order
        # for free, which is exactly what gap_for() wants.
        r = self._t.query(
            KeyConditionExpression=Key("PK").eq("FIXTURE#%s" % fixture_id)
                                   & Key("SK").begins_with("EVENT#"))
        out = [Event(from_ddb(i["data"])) for i in r.get("Items", [])]
        # Same order as MemoryStore: minute, then when we logged it.
        out.sort(key=lambda e: (e["minute"], e.get("at") or 0))
        return out

    def fixture(self, fixture_id):
        r = self._t.get_item(
            Key={"PK": "FIXTURE#%s" % fixture_id, "SK": "META"}).get("Item")
        return from_ddb(r["data"]) if r else None

    def followers(self, fixture_id):
        r = self._t.query(
            KeyConditionExpression=Key("PK").eq("FOLLOWERS#%s" % fixture_id)
                                   & Key("SK").begins_with("LISTENER#"))
        ids = [i["SK"][len("LISTENER#"):] for i in r.get("Items", [])]
        # Drop markers left by listeners who have since followed another match.
        return sorted(i for i in ids if self.listener(i).get("following") == fixture_id)

    def all_followed_fixtures(self):
        """Fixtures at least one listener is following right now: what the poller polls.

        INDEX#FOLLOWED lists every fixture ever saved, so each is checked against its followers
        (the same marker-then-profile check `followers` does). Without that, every match anyone ever
        followed would be polled for ever, against a feed that allows a few hundred calls an hour.
        The set is small and bounded by how many matches one server has seen, and it needs no scan.
        """
        r = self._t.query(
            KeyConditionExpression=Key("PK").eq("INDEX#FOLLOWED")
                                   & Key("SK").begins_with("FIXTURE#"))
        indexed = {from_ddb(i["data"])["fixture_id"] for i in r.get("Items", [])}
        return sorted(f for f in indexed if self.followers(f))

    # ----------------------------------------------------------- writes
    def save_listener(self, rec):
        self._t.put_item(Item={"PK": "LISTENER#" + rec["listener_id"],
                               "SK": "PROFILE", "data": to_ddb(rec)})
        if rec.get("following"):
            # A marker so "who follows this fixture" is a Query, not a
            # scan. Stale markers (a listener who switched match) expire
            # with the TTL and are filtered on read.
            import time
            self._t.put_item(Item={
                "PK": "FOLLOWERS#%s" % rec["following"],
                "SK": "LISTENER#%s" % rec["listener_id"],
                "expires_at": int(time.time()) + 48 * 3600})
        # Last-write-wins is correct here: a listener is one person with
        # one voice. Concurrent writes to the same profile do not happen,
        # and a conditional write would buy nothing but latency.
        return rec

    def append_event(self, event):
        # The one place a condition expression genuinely earns its keep.
        # The poller re-reads an overlapping window every cycle; without
        # this the listener is told about the same goal on every poll.
        import time
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
        return event

    def supersede(self, fixture_id, event_id, by_event_id):
        import time
        for e in self.events(fixture_id):
            if e["id"] == event_id:
                e["superseded_by"] = by_event_id
                self._t.put_item(
                    Item={"PK": "FIXTURE#%s" % fixture_id,
                          "SK": event_sk(e),
                          "expires_at": int(time.time()) + 48 * 3600,
                          "data": to_ddb(e)})
                return e
        return None

    def save_fixture(self, rec):
        self._t.put_item(Item={"PK": "FIXTURE#%s" % rec["fixture_id"],
                               "SK": "META", "data": to_ddb(rec)})
        self._t.put_item(Item={"PK": "INDEX#FOLLOWED",
                               "SK": "FIXTURE#%s" % rec["fixture_id"],
                               "data": {"fixture_id": rec["fixture_id"]}})
        return rec
