#!/usr/bin/env python3
"""Check the AWS integrations, one layer at a time.

    python3 scripts/verify_aws.py        # or: make aws-check

Run this BEFORE the server. It uses small synthetic inputs, not football data, so
it needs no feed key and checks the integration, not the match. It makes a few
tiny paid calls (a fraction of a cent). Exits 0 when everything required works.

Required: boto3, credentials, a Bedrock model, a live Bedrock answer, Nova calling
a Sideline tool, and a catch-up written by Bedrock. Reported but not required:
speech in, speech out, DynamoDB (the server falls back to the browser's voice and
to in-memory state).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sideline  # noqa: E402,F401  (loads .env, bridges AWS_REGION)

OK, BAD, SKIP = "  ok ", " FAIL", " skip"
_failed = []


def check(label, fn, needed=True):
    try:
        detail = fn()
    except Exception as e:                                     # noqa: BLE001
        print("%s  %-34s %s" % (BAD if needed else SKIP, label, e))
        if needed:
            _failed.append(label)
        return False
    print("%s  %-34s %s" % (OK, label, detail or ""))
    return True


# ---------------------------------------------------------------- checks
def _boto3():
    import boto3
    return "boto3 %s" % boto3.__version__


def _credentials():
    import boto3
    return "account %s" % boto3.client("sts").get_caller_identity()["Account"]


def _region():
    import boto3
    r = boto3.session.Session().region_name
    if not r:
        raise RuntimeError("no region set - export AWS_REGION (e.g. us-east-1)")
    return r


def _model_access():
    import boto3
    from sideline.language.bedrock import MODEL_ID, REGION
    bedrock = boto3.client("bedrock", region_name=REGION)
    ids = [m["modelId"] for m in bedrock.list_foundation_models().get("modelSummaries", [])]
    profiles = []
    try:    # some models are invoked through inference profiles, not bare ids
        profiles = [p["inferenceProfileId"] for p in
                    bedrock.list_inference_profiles().get("inferenceProfileSummaries", [])]
    except Exception:                                          # noqa: BLE001
        pass
    if MODEL_ID not in ids and MODEL_ID not in profiles:
        available = sorted(i for i in ids + profiles if "nova" in i.lower()) or sorted(ids)
        raise RuntimeError(
            "%s is not available in %s. Enable it in the Bedrock console, or pick one this "
            "account can see and export SIDELINE_BEDROCK_MODEL=<id>:\n%s"
            % (MODEL_ID, REGION, "\n".join("         " + i for i in available[:8])))
    return MODEL_ID


def _invoke():
    """One real call: the only thing that proves the whole chain."""
    import time
    from sideline.language import bedrock
    if not bedrock.available():
        raise RuntimeError("Bedrock is off (SIDELINE_BEDROCK=off, or no AWS credentials)")
    t0 = time.time()
    out = bedrock._converse("Reply with exactly the word: ready", "ready?", max_tokens=12)
    return '"%s" in %dms' % (out[:30], (time.time() - t0) * 1000)


def _synthetic_match():
    """A made-up fixture and events: this checks Bedrock, not the football feed."""
    fixture = {"fixture_id": 1, "home": "Harbour FC", "away": "Reef United",
               "minute": 64, "status": "live", "score": {"home": 2, "away": 1}}
    events = [
        {"id": "e1", "minute": 12, "kind": "goal", "player": "A. Vale", "team": "Harbour FC"},
        {"id": "e2", "minute": 31, "kind": "card", "player": "B. Quill", "team": "Reef United",
         "colour": "yellow"},
        {"id": "e3", "minute": 58, "kind": "goal", "player": "C. Banner", "team": "Reef United"},
        {"id": "e4", "minute": 61, "kind": "goal", "player": "A. Vale", "team": "Harbour FC"},
    ]
    return fixture, events


def _catchup_path():
    """Does a catch-up actually go through the model, and pass the score guard?"""
    from sideline.language import bedrock
    fixture, events = _synthetic_match()
    text, how = bedrock.catchup(events, fixture, 10, 64)
    if how != "bedrock":
        raise RuntimeError("catch-up came back via '%s', not bedrock" % how)
    return '%d events -> "%s"' % (len(events), text[:60])


def _agent_path():
    """Can Nova choose and call a registered Sideline tool?"""
    from sideline.language.agent import run
    calls = []

    def stub(name, args, listener):
        calls.append(name)
        return "Following Harbour FC against Reef United. 2 1, 64 minutes in.", {}, None
    run(None, "Follow the Harbour FC game.", "verify-aws", stub)
    if "follow_match" not in calls:
        raise RuntimeError("Nova answered without calling follow_match; it called %s" % calls)
    return "Nova called %s" % ", ".join(calls)


def _tts_live():
    from sideline import voice
    out = voice.synthesize("Sideline speech check.")
    if not out or not out.get("audio"):
        raise RuntimeError("Polly returned no audio")
    return "polly %s: %d bytes of audio, %d word marks" % (
        voice.POLLY_VOICE, len(out["audio"]), len(out.get("marks") or []))


def _stt_round_trip():
    """Polly says a phrase; the active speech-in model (Voxtral or Nova Sonic) must hear it."""
    import boto3

    from sideline import voice
    pcm = boto3.client("polly", region_name=voice.REGION).synthesize_speech(
        Text="Who is refereeing the match?", OutputFormat="pcm", SampleRate="16000",
        VoiceId="Joanna", Engine="neural")["AudioStream"].read()
    out = voice.transcribe(pcm, "audio/pcm", voice._BASE_HINT)
    if not out or "refereeing" not in out["text"].lower():
        raise RuntimeError("%s returned %r" % (voice.capabilities()["stt"], out and out["text"]))
    return "%s heard %r" % (out["provider"], out["text"])


def _dynamo():
    import boto3
    from sideline.config import CONFIG
    status = boto3.resource("dynamodb", region_name=CONFIG.region).Table(CONFIG.table).table_status
    return "%s is %s in %s" % (CONFIG.table, status, CONFIG.region)


# ------------------------------------------------------------------ run
def main():
    print("\nSideline - AWS check\n" + "-" * 56)
    if not check("boto3 installed", _boto3):
        print("\n  pip3 install boto3\n")
        return 1
    check("credentials resolve", _credentials)
    check("region set", _region)

    if check("bedrock model access", _model_access):
        if check("bedrock responds", _invoke):
            check("Nova MCP agent tool use", _agent_path)
            check("catch-up written by bedrock", _catchup_path)

    from sideline.voice import capabilities
    caps = capabilities()
    if caps["stt"]:
        check("speech in (%s, live call)" % caps["stt"], _stt_round_trip, needed=False)
    else:
        print("%s  %-34s %s" % (SKIP, "speech in", caps.get("stt_hint", "browser fallback")))
    if caps["tts"]:
        check("speech out (Polly, live call)", _tts_live, needed=False)
    else:
        print("%s  %-34s %s" % (SKIP, "speech out", caps.get("tts_hint", "browser fallback")))

    from sideline.config import CONFIG
    if CONFIG.state in ("dynamo", "auto"):
        check("dynamodb table", _dynamo, needed=False)
    else:
        print("%s  %-34s SIDELINE_STATE=memory" % (SKIP, "dynamodb"))

    print("-" * 56)
    if _failed:
        print("failed: %s\n\nSee docs/AWS_SETUP.md.\n" % ", ".join(_failed))
        return 1
    print("all good: python3 -m sideline\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
