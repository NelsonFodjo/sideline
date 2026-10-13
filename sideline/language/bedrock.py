"""Amazon Bedrock - where language has to be composed rather than stated.

Alexa+ only ever sees what we return, so any reasoning that has to happen
BEFORE the response leaves this server has to happen here. The catch-up is the
case: eleven minutes of a match can hold nine raw events, and returning nine
lines gives Alexa+ a list that sounds like a spreadsheet read aloud. Deciding
what mattered and leading with the goal is a judgement made here.

One rule governs failure: if Bedrock is on, a failure is reported to the caller
(BedrockUnavailable) and never papered over with canned wording; if Bedrock is
off (SIDELINE_BEDROCK=off, or no AWS credentials), the deterministic templates
in templates.py are used and the response says `generated_by: template`.

Where it is used:
    catchup()     events since the listener last heard, as one spoken paragraph
    milestones()  a long absence, reduced to headlines plus an offer
    translate()   the same facts in another language or register
and where it is not: a scoreline, the line-ups, the officials, one event. Those
are facts, so they are templated (fast, and nothing to get wrong). The voice
agent (agent.py) is separate: Nova there chooses which tool to call.

Nova Micro, not a larger model: this is compression under a voice deadline, not
writing. max_attempts=1, because a retry costs another request timeout. A
catch-up takes about two seconds, which misses Alexa+'s 500 ms target; that is
stated in the README rather than hidden.

Spoken length is a target rather than a hard truncation: cutting a sentence
mid-clause to hit a word count produces something nobody can follow. A gap too
large to fit goes through milestones() instead.
"""

import json
import logging
import os

from .. import config, sports
from . import templates
from .prompts import CATCHUP_SYSTEM, MILESTONE_SYSTEM, TRANSLATE_SYSTEM

LOG = logging.getLogger("sideline.bedrock")

# Imported at module level so the dependency is visible, and guarded so the
# repository still imports on a machine without boto3.
try:
    import boto3
    from botocore.config import Config as BotoConfig
    HAVE_BOTO3 = True
except ImportError:                                            # pragma: no cover
    boto3 = None
    BotoConfig = None
    HAVE_BOTO3 = False

# SIDELINE_BEDROCK: auto (on when AWS credentials are present), on, or off.
ENABLED = config.bedrock_enabled()
REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ.get("SIDELINE_BEDROCK_MODEL", "amazon.nova-micro-v1:0")

TIMEOUT_SECONDS = 8.0
MAX_TOKENS = 160
MAX_EVENTS_IN_PROMPT = 12
SPOKEN_WORD_TARGET = 45

_client = None


class BedrockUnavailable(Exception):
    """Bedrock is on but could not produce a usable answer."""


class _Refused(BedrockUnavailable):
    """The model answered, but the text was not usable (empty, or a wrong score).

    Unlike a failed request this is quick and often not repeated, so one retry is
    worth it. A timeout or an error is not retried: that costs another timeout.
    """


def client():
    """Lazily initialise the Bedrock runtime client.

    Lazy because constructing it resolves credentials, and importing this module
    must not touch the filesystem or the metadata service.
    """
    global _client
    if _client is None:
        if not HAVE_BOTO3:
            return None
        _client = boto3.client(
            "bedrock-runtime",
            region_name=REGION,
            config=BotoConfig(read_timeout=TIMEOUT_SECONDS, connect_timeout=1.0,
                              retries={"max_attempts": 1}))
        LOG.info("bedrock-runtime client ready: %s in %s", MODEL_ID, REGION)
    return _client


def available():
    return ENABLED and HAVE_BOTO3


def _converse(system, user_text, max_tokens=MAX_TOKENS):
    """One streamed Converse call. Returns the text, or raises BedrockUnavailable."""
    import time
    c = client()
    if c is None:
        raise BedrockUnavailable("Bedrock client is unavailable")
    t0 = time.time()
    try:
        resp = c.converse_stream(
            modelId=MODEL_ID,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user_text}]}],
            inferenceConfig={"maxTokens": max_tokens,
                             "temperature": 0.2,   # reporting, not writing
                             "topP": 0.9},
        )
        pieces = []
        for event in resp.get("stream"):
            delta = event.get("contentBlockDelta", {}).get("delta", {})
            if delta.get("text"):
                pieces.append(delta["text"])
        out = "".join(pieces).strip()
        LOG.info("bedrock %s answered in %dms", MODEL_ID, (time.time() - t0) * 1000)
        return out
    except Exception as e:                                     # noqa: BLE001
        LOG.error("bedrock request failed: %s", e)
        raise BedrockUnavailable("Bedrock request failed") from e


# ----------------------------------------------------------- public API
def _system(template, fixture):
    return template.format(domain=sports.resolve(fixture).domain)


def key_events(events, fixture=None):
    """The headline events a long absence is reduced to: the sport's call
    (goals and reds in football, threes and ejections in basketball)."""
    return sports.resolve(fixture).headlines(events)


def catchup(events, fixture, from_minute, to_minute):
    """Events since the listener last heard, as one spoken paragraph.

    Returns (text, generated_by): "bedrock", or "template" when Bedrock is off.
    """
    if not available():
        return templates.say_catchup(events, fixture, from_minute, to_minute), "template"
    if not events:
        raise BedrockUnavailable("No events were supplied for a catch-up")
    payload = {
        "score": templates.say_score(fixture),
        "from_minute": from_minute,
        "to_minute": to_minute,
        "word_budget": SPOKEN_WORD_TARGET,
        "events": [_slim(e) for e in events[:MAX_EVENTS_IN_PROMPT]],
    }
    return _write(_system(CATCHUP_SYSTEM, fixture), payload, fixture), "bedrock"


def milestones(events, fixture, minutes_away):
    """A long absence, compressed to headlines plus an offer.

    Forty minutes of match read back in full is a wall of text nobody can follow
    by ear: we give what changed the game and let the listener ask for the rest.
    """
    key = key_events(events, fixture)
    if not available():
        return templates.say_milestones(key, events, fixture, minutes_away), "template"
    if not events:
        raise BedrockUnavailable("No events were supplied for milestones")
    payload = {"score": templates.say_score(fixture),
               "minutes_away": minutes_away,
               "other_event_count": len(events) - len(key),
               "word_budget": SPOKEN_WORD_TARGET,
               "key_events": [_slim(e) for e in key[:sports.MAX_HEADLINES]]}
    return _write(_system(MILESTONE_SYSTEM, fixture), payload, fixture), "bedrock"


def translate(text, language):
    """Render the same facts in another language or register.

    'pidgin' and 'sheng' are registers a listener may genuinely prefer, and a
    match fact in the voice people use around them is a different experience from
    formal broadcast English. Names are never translated.
    """
    if language in (None, "", "en") or not available():
        return text, "template"
    out = _converse(TRANSLATE_SYSTEM.format(language=language), text)
    if not out:
        raise BedrockUnavailable("Bedrock could not translate the answer")
    return out, "bedrock"


# ------------------------------------------------------------- helpers
_KEEP = ("minute", "stoppage", "kind", "player", "player_off", "team",
         "assist", "detail", "colour", "reason", "decision", "points")


def _slim(e):
    """Only the fields the model needs: a smaller prompt, lower latency, and
    fewer fields it could be tempted to embellish."""
    return {k: v for k, v in e.items() if k in _KEEP and v not in (None, "")}


def _write(system, payload, fixture):
    """Ask the model, check what it said, and try once more if the text was refused."""
    message = json.dumps(payload, ensure_ascii=False)
    try:
        return _checked(_converse(system, message), fixture)
    except _Refused as first:
        LOG.warning("bedrock text refused (%s); retrying once", first)
        return _checked(_converse(system, message), fixture)


def _checked(text, fixture):
    """The model's text if it is usable, else _Refused (a BedrockUnavailable)."""
    if not text:
        raise _Refused("Bedrock returned no text")
    if not _score_consistent(text, fixture):
        LOG.warning("bedrock output disagreed with the score; discarding")
        raise _Refused("Bedrock returned an inconsistent score")
    return text


def _score_consistent(text, fixture):
    """Does the generated text contradict the real score?

    Prompting is necessary but not sufficient. A product whose whole claim is that
    it knows what is happening right now is destroyed by one invented scoreline,
    so there is a check as well as an instruction. Conservative: only rejects when
    the text states a parseable scoreline AND it disagrees.
    """
    import re
    h, a = fixture["score"]["home"], fixture["score"]["away"]
    for x, y in re.findall(r"(\d+)\s*[-–]\s*(\d+)", text):
        if {int(x), int(y)} != {h, a}:
            return False
    return True
