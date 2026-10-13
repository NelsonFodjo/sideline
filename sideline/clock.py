"""The current time, and when a fixture starts.

One place for it, so a test can pin "now" (`clock.now = lambda: ...`) and no
other module reads the system clock to answer a listener.

Times are timezone-aware. The feed gives kickoff in UTC; anything spoken as a
clock time ("at 11:45") is in the SERVER MACHINE'S local zone, which is the
listener's own when the server runs on their machine, as it does here. Relative
phrasing ("in two hours") is zone-free, so it leads.
"""

import datetime

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


def local_clock(dt):
    """The wall-clock time of `dt` in the server machine's zone, as "11:45"."""
    return dt.astimezone().strftime("%H:%M")


def say_kickoff(fixture, start_word="kick-off", at=None):
    """When the match starts, as a sentence; "" when the feed gave no time.

        "Kick-off is in 2 hours 15 minutes, at 11:45."
        "Kick-off was due 10 minutes ago."
    """
    ko = kickoff(fixture)
    if ko is None:
        return ""
    delta = ko - (at or now())
    word = start_word[:1].upper() + start_word[1:]
    if delta.total_seconds() >= 30:
        return "%s is in %s, at %s." % (word, say_duration(delta), local_clock(ko))
    if delta.total_seconds() > -30:
        return "%s is about to happen." % word
    return "%s was due %s ago." % (word, say_duration(delta))


def snapshot(fixture, at=None):
    """Structured form for tool results: the time now and the fixture's start."""
    at = at or now()
    ko = kickoff(fixture)
    delta = (ko - at) if ko else None
    return {"now": at.isoformat(),
            "kickoff": ko.isoformat() if ko else None,
            "minutes_to_kickoff": int(delta.total_seconds() // 60) if delta is not None else None}
