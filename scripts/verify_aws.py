#!/usr/bin/env python3
"""Check the AWS setup, one layer at a time.

    python scripts/verify_aws.py

Run this BEFORE the server, not after. The language layer degrades
silently to templates by design, so a misconfigured Bedrock looks
exactly like a working Sideline until you notice the answers are a bit
flat. This tells you which layer actually failed.

Exits 0 when everything needed is working, 1 otherwise. Nothing here
writes, charges or creates anything except one tiny Bedrock call at the
end, which costs a fraction of a cent.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sideline  # noqa: E402,F401  (bridges AWS_REGION -> AWS_DEFAULT_REGION)

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
    bearer = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
    if bearer:
        return "Bedrock API Key (bearer token configured)"
    ident = boto3.client("sts").get_caller_identity()
    return "account %s" % ident["Account"]


def _region():
    import boto3
    r = boto3.session.Session().region_name
    if not r:
        raise RuntimeError("no region set - export AWS_REGION (e.g. us-east-1)")
    if r != "us-east-1":
        return "%s  (us-east-1 has the widest model availability)" % r
    return r


def _model_access():
    import boto3
    from sideline.language.bedrock import MODEL_ID, REGION
    bedrock = boto3.client("bedrock", region_name=REGION)
    models = bedrock.list_foundation_models().get("modelSummaries", [])
    ids = [m["modelId"] for m in models]
    # Newer models are called through an inference profile (an id such as
    # "us.anthropic.claude-...") rather than the bare foundation-model id.
    profiles = []
    try:
        profiles = [p["inferenceProfileId"] for p in
                    bedrock.list_inference_profiles().get("inferenceProfileSummaries", [])]
    except Exception:                                          # noqa: BLE001
        pass                      # older boto3, or no permission: not fatal
    if MODEL_ID not in ids and MODEL_ID not in profiles:
        claude = sorted(i for i in ids + profiles if "anthropic" in i)
        haiku = [i for i in claude if "haiku" in i] or claude
        raise RuntimeError(
            "%s not available in %s.\n"
            "       Console -> Bedrock -> Model access -> enable the model, or\n"
            "       pick one this account can see and export it:\n"
            "%s\n"
            "       export SIDELINE_BEDROCK_MODEL=<one of the above>\n"
            "       (this is the step everyone misses; the invoke error looks\n"
            "       like a permissions problem but it is not)"
            % (MODEL_ID, REGION,
               "\n".join("         " + i for i in haiku[:8]) or
               "         (none listed: access not granted yet)"))
    return MODEL_ID


def _invoke():
    """One real call. The only thing that proves the whole chain."""
    import time
    from sideline.language import bedrock
    if not bedrock.ENABLED:
        raise RuntimeError("SIDELINE_BEDROCK is off - export SIDELINE_BEDROCK=on")
    t0 = time.time()
    out = bedrock._converse(
        "Reply with exactly the word: ready", "ready?", max_tokens=12)
    if not out:
        raise RuntimeError("call returned nothing - see the warning logged above")
    return '"%s"  in %dms' % (out[:30], (time.time() - t0) * 1000)


def _catchup_path():
    """End to end: does a real catch-up actually go through the model?"""
    from tests.conftest import make_ctx
    from sideline.poller import poll_once
    from sideline.tools import REGISTRY
    from sideline import summaries
    summaries.MODE = "live"
    ctx = make_ctx(start_minute=70)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "verify")
    poll_once(ctx)
    _, s, _ = REGISTRY["what_did_i_miss"](ctx, {}, "verify")
    how = s["generated_by"]
    if how != "bedrock":
        raise RuntimeError(
            "catch-up came back via '%s', not bedrock.\n"
            "       'template' means it fell back; 'template-after-guard'\n"
            "       means the model contradicted the score and we discarded it."
            % how)
    return "%d events compressed via bedrock" % s["event_count"]


def _dynamo():
    import boto3
    endpoint = os.environ.get("SIDELINE_DYNAMO_ENDPOINT")
    table = os.environ.get("SIDELINE_TABLE", "sideline")
    kw = {"region_name": os.environ.get("AWS_REGION", "us-east-1")}
    if endpoint:
        kw["endpoint_url"] = endpoint
    t = boto3.resource("dynamodb", **kw).Table(table)
    status = t.table_status
    where = endpoint or kw["region_name"]
    return "%s is %s at %s" % (table, status, where)


# ------------------------------------------------------------------ run
def main():
    print("\nSideline - AWS check\n" + "-" * 56)

    if not check("boto3 installed", _boto3):
        print("\n  pip install boto3\n")
        return 1
    check("credentials resolve", _credentials)
    check("region set", _region)

    bedrock_on = os.environ.get("SIDELINE_BEDROCK", "off").lower() == "on"
    if not bedrock_on:
        print("%s  %-34s SIDELINE_BEDROCK is off - templates only" % (SKIP, "bedrock"))
        print("       export SIDELINE_BEDROCK=on to turn the language layer on")
    else:
        if check("bedrock model access", _model_access):
            if check("bedrock responds", _invoke):
                check("catch-up runs through bedrock", _catchup_path)

    # Voice: simulator only, but it is the difference between a
    # speech-first demo and a typed one.
    from sideline.voice import capabilities
    caps = capabilities()
    if caps["stt"]:
        print("%s  %-34s %s" % (OK, "speech in", caps["stt"]))
    else:
        print("%s  %-34s %s" % (SKIP, "speech in",
                                caps.get("stt_hint", "browser fallback")))
    if caps["tts"]:
        print("%s  %-34s polly %s (%s)" % (OK, "speech out",
                                           caps["voice"], caps["engine"]))
    else:
        print("%s  %-34s %s" % (SKIP, "speech out",
                                caps.get("tts_hint", "browser fallback")))

    if os.environ.get("SIDELINE_STATE") == "dynamo":
        check("dynamodb reachable", _dynamo)
    else:
        print("%s  %-34s SIDELINE_STATE=memory (fine for a demo)"
              % (SKIP, "dynamodb"))

    print("-" * 56)
    if _failed:
        print("failed: %s\n\nSee docs/AWS_SETUP.md - the table at the bottom maps\n"
              "every error above to its cause.\n" % ", ".join(_failed))
        return 1
    print("all good. `python -m sideline`\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
