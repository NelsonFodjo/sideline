"""The current time, and when a fixture starts.

One place for it, so a test can pin "now" (`clock.now = lambda: ...`) and no
other module reads the system clock to answer a listener.

Times are timezone-aware. The feed gives kickoff in UTC. A clock time is spoken
in the LISTENER'S zone when the page told us its offset (`tz_offset_minutes`), and
in UTC, said so, when it did not: never a guess. "At 10 PM, in about 11 hours."
"""

import datetime

from .status import FINISHED

UTC = datetime.timezone.utc


def now():
    """The current moment, timezone-aware (UTC)."""
    return datetime.datetime.now(UTC)


def parse(iso):
    """An ISO 8601 timestamp as an aware datetime, or None if there is none.

    Accepts a trailing "Z", which datetime.fromisoformat only learned in 3.11
    (CI still runs 3.8). A timestamp with no zone is taken as UTC.
    """
    if not iso or not isinstance(iso, str):
        return None
    try:
        dt = datetime.datetime.fromisoformat(iso.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def kickoff(fixture):
    """When the fixture is due to start, or None if the feed gave no time."""
    return parse((fixture or {}).get("kickoff"))


def until_kickoff(fixture, at=None):
    """Time from `at` (default: now) to kickoff. Negative once it is past; None if unknown."""
    ko = kickoff(fixture)
    if ko is None:
        return None
    return ko - (at or now())


def say_duration(delta):
    """A span as people say it: "2 hours 15 minutes", "45 minutes", "1 day 3 hours".

    Rounded to the minute, and to the hour once it is more than a day away: nobody
    wants "1 day 3 hours 12 minutes". Under a minute is "less than a minute".
    """
    seconds = int(abs(delta.total_seconds()))
    minutes = (seconds + 30) // 60
    if minutes < 1:
        return "less than a minute"
    days, rest = divmod(minutes, 24 * 60)
    hours, mins = divmod(rest, 60)
    parts = []
    if days:
        parts.append("%d day%s" % (days, "" if days == 1 else "s"))
        if hours:
            parts.append("%d hour%s" % (hours, "" if hours == 1 else "s"))
    else:
        if hours:
            parts.append("%d hour%s" % (hours, "" if hours == 1 else "s"))
        if mins:
            parts.append("%d minute%s" % (mins, "" if mins == 1 else "s"))
    return " ".join(parts)


class Zone(int):
    """A listener's offset from UTC in minutes (so it works anywhere an int does), plus the
    name their browser gave it ("Indian/Mauritius"), which is what lets a time be said as
    "10 PM Mauritius time"."""

    def __new__(cls, minutes, name=None):
        z = super().__new__(cls, int(minutes))
        z.name = name
        return z


def zone_from(d):
    """The listener's Zone from a record or fixture that carries tz_offset_minutes (and tz_name)."""
    minutes = (d or {}).get("tz_offset_minutes")
    return None if minutes is None else Zone(minutes, (d or {}).get("tz_name"))


# How a zone is said. Only where the common name differs from the city: the rest say the city.
_FRIENDLY = {
    "Indian/Mauritius": "Mauritius", "Asia/Kolkata": "India", "Asia/Calcutta": "India",
    "Europe/London": "UK", "Europe/Dublin": "Irish", "Asia/Dubai": "Dubai",
    "America/New_York": "US Eastern", "America/Detroit": "US Eastern", "America/Toronto": "Eastern",
    "America/Chicago": "US Central", "America/Denver": "US Mountain", "America/Phoenix": "US Mountain",
    "America/Los_Angeles": "US Pacific", "America/Anchorage": "Alaska", "Pacific/Honolulu": "Hawaii",
    "America/Sao_Paulo": "Brazil", "Africa/Johannesburg": "South Africa", "Asia/Shanghai": "China",
    "Asia/Tokyo": "Japan", "Asia/Seoul": "Korea", "Asia/Singapore": "Singapore",
    "Australia/Sydney": "Sydney", "Australia/Melbourne": "Melbourne", "Pacific/Auckland": "New Zealand",
    "UTC": "UTC", "Etc/UTC": "UTC", "GMT": "UTC",
}


def zone_label(name):
    """"Mauritius time", "India time", "US Eastern time"; "" when the browser gave no name."""
    if not name or not isinstance(name, str):
        return ""
    if name in _FRIENDLY:
        said = _FRIENDLY[name]
    elif name.startswith(("America/Indiana/", "America/Kentucky/")):
        said = "US Eastern"
    else:
        said = name.split("/")[-1].replace("_", " ")
    return "UTC" if said == "UTC" else "%s time" % said


def zone_phrase(tz=None):
    """The zone once, for the top of a list: "Mauritius time", or "UTC" when no zone is known."""
    return "UTC" if tz is None else zone_label(getattr(tz, "name", None))


def zone(tz_minutes=None):
    """The listener's zone as a fixed offset from UTC; UTC when it is not known."""
    if tz_minutes is None:
        return UTC
    return datetime.timezone(datetime.timedelta(minutes=int(tz_minutes)))


def say_zone(tz_minutes=None):
    """The zone as it is said: "UTC", "UTC plus 4", "UTC minus 5", "UTC plus 5:30"."""
    if not tz_minutes:
        return "UTC"
    sign = "plus" if tz_minutes > 0 else "minus"
    hours, mins = divmod(abs(int(tz_minutes)), 60)
    return "UTC %s %d%s" % (sign, hours, ":%02d" % mins if mins else "")


def say_time_of_day(dt, tz_minutes=None, with_zone=True):
    """"10 PM Mauritius time", "5 PM US Eastern time", "7:45 AM UTC".

    The zone is named the way people name it. With only an offset (no name) there is nothing
    friendly to say, so the time stands alone; with no zone at all it is UTC and says so, so it is
    never mistaken for local time. `with_zone=False` leaves the label off (a list says it once)."""
    t = dt.astimezone(zone(tz_minutes))
    hour = t.hour % 12 or 12
    text = "%d %s" % (hour, "AM" if t.hour < 12 else "PM") if t.minute == 0 else \
        "%d:%02d %s" % (hour, t.minute, "AM" if t.hour < 12 else "PM")
    if not with_zone:
        return text
    label = "UTC" if tz_minutes is None else zone_label(getattr(tz_minutes, "name", None))
    return "%s %s" % (text, label) if label else text


def say_day(dt, at=None, tz_minutes=None):
    """"today", "tomorrow", "yesterday", "on Saturday" or "on 20 October", in the listener's zone."""
    z = zone(tz_minutes)
    day = dt.astimezone(z).date()
    gap = (day - (at or now()).astimezone(z).date()).days
    if gap == 0:
        return "today"
    if gap == 1:
        return "tomorrow"
    if gap == -1:
        return "yesterday"
    if 1 < gap < 7:
        return "on " + day.strftime("%A")
    return "on %d %s" % (day.day, day.strftime("%B"))


def say_roughly(delta):
    """How far away, loosely: "25 minutes", "about 11 hours", "about 3 days"."""
    minutes = int(abs(delta.total_seconds()) // 60)
    if minutes < 90:
        return "%d minute%s" % (minutes, "" if minutes == 1 else "s")
    hours = int(round(minutes / 60.0))
    if hours < 48:
        return "about %d hours" % hours
    return "about %d days" % int(round(hours / 24.0))


def say_kickoff(fixture, start_word="kick-off", at=None, tz_minutes=None):
    """When the match starts, as a sentence; "" when the feed gave no time.

        "Kick-off is today at 10 PM, in about 11 hours."
        "Kick-off is tomorrow at 7:45 PM, in about 21 hours."
        "Kick-off is about to happen."
        "Kick-off was due 10 minutes ago."
    """
    ko = kickoff(fixture)
    if ko is None:
        return ""
    at = at or now()
    delta = ko - at
    word = start_word[:1].upper() + start_word[1:]
    if delta.total_seconds() >= 30:
        return "%s is %s at %s, in %s." % (
            word, say_day(ko, at, tz_minutes), say_time_of_day(ko, tz_minutes), say_roughly(delta))
    if delta.total_seconds() > -30:
        return "%s is about to happen." % word
    return "%s was due %s ago." % (word, say_duration(delta))


def say_fixture(fx, tz_minutes=None, at=None, with_day=True, with_zone=True):
    """A match as it is read out, always with its time:

        "Arsenal against Lille, today at 11 PM"
        "Arsenal against Lille at 11 PM"            (with_day=False, in a list for today)
        "Chelsea against Fulham, live, 34 minutes in"
        "Brighton against Everton, finished"
    """
    names = "%s against %s" % (fx.get("home"), fx.get("away"))
    if fx.get("status") in FINISHED:
        sc = fx.get("score")
        if sc and sc.get("home") is not None and sc.get("away") is not None:
            return "%s %d, %s %d, finished" % (fx.get("home"), sc["home"], fx.get("away"), sc["away"])
        return names + ", finished"
    minute = fx.get("minute") or 0
    if minute > 0:
        return "%s, live, %d minutes in" % (names, minute)
    ko = kickoff(fx)
    if ko is None:
        return names
    at = at or now()
    delta = ko - at
    clock_time = say_time_of_day(ko, tz_minutes, with_zone)
    if delta.total_seconds() >= 30:
        return ("%s, %s at %s" % (names, say_day(ko, at, tz_minutes), clock_time) if with_day
                else "%s at %s" % (names, clock_time))
    if delta.total_seconds() > -30:
        return "%s, starting now" % names
    return "%s, was due to start at %s" % (names, clock_time)


def snapshot(fixture, at=None):
    """Structured form for tool results: the time now and the fixture's start."""
    at = at or now()
    ko = kickoff(fixture)
    delta = (ko - at) if ko else None
    return {"now": at.isoformat(),
            "kickoff": ko.isoformat() if ko else None,
            "minutes_to_kickoff": int(delta.total_seconds() // 60) if delta is not None else None}
