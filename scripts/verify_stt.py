#!/usr/bin/env python3
"""Measure speech-to-text on football phrases, with and without the match vocabulary.

    python3 scripts/verify_stt.py            # whichever provider is configured
    SIDELINE_STT=voxtral python3 scripts/verify_stt.py

Polly speaks each phrase in several voices (needs AWS credentials), the
configured speech-to-text provider transcribes it, and we print what it heard
and a word error rate (0% is perfect). Synthetic speech is cleaner than a
person in a room with a television on, so treat the result as an upper bound
on accuracy, not a promise. It is still the quickest way to see whether the
provider gets names like Ødegaard and Alderweireld right, and whether the
vocabulary prompt helps. Compare with the browser by saying the same phrases
into the simulator.
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sideline  # noqa: E402,F401  (loads .env)
from sideline import voice  # noqa: E402

PHRASES = [
    "What's the score?",
    "Who is refereeing, and what did I miss since half time?",
    "Tell me about that goal.",
    "Who is Martin Ødegaard?",
    "Has Toby Alderweireld been booked?",
    "Kick-off just went.",
    "What was the VAR decision on Bukayo Saka's goal?",
    "Is Héctor Bellerín playing today?",
]
NAMES = ("Arsenal, Tottenham Hotspur, Martin Ødegaard, Toby Alderweireld, "
         "Bukayo Saka, Héctor Bellerín, Harry Kane")
VOICES = [("Amy", "en-GB"), ("Brian", "en-GB"), ("Joanna", "en-US")]


def words(s):
    return re.sub(r"[^a-z0-9' ]+", " ", s.lower().replace("ø", "o").replace("é", "e")
                  .replace("í", "i")).split()


def wer(ref, hyp):
    r, h = words(ref), words(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / float(max(1, len(r)))


def speak(text, voice_id):
    import boto3
    pcm = boto3.client("polly", region_name=voice.REGION).synthesize_speech(
        Text=text, OutputFormat="pcm", SampleRate="16000", VoiceId=voice_id,
        Engine="neural")["AudioStream"].read()
    return pcm


def main():
    which = voice.capabilities()["stt"]
    if not which:
        print("no speech-to-text provider configured: set AWS credentials (Voxtral on Bedrock)")
        return 1
    model = {"voxtral": voice.VOXTRAL_MODEL, "sonic": voice.SONIC_MODEL}.get(which)
    print("provider: %s%s\n" % (which, " (%s)" % model if model else ""))
    totals = {"plain": [], "hint": []}
    for text in PHRASES:
        for vid, _ in VOICES:
            pcm = speak(text, vid)
            row = []
            for label, hint in (("plain", ""), ("hint", voice._BASE_HINT + " " + NAMES)):
                if which not in ("voxtral", "sonic") and label == "hint":
                    continue
                out = voice.transcribe(pcm, "audio/pcm", hint)
                if out is None and not totals["plain"] and not totals["hint"]:
                    print("the first clip came back empty: %s is not working (see the "
                          "warning above). Nothing to measure." % which)
                    return 1
                heard = out["text"] if out else ""
                w = wer(text, heard)
                totals[label].append(w)
                row.append((label, w, heard))
            bad = [r for r in row if r[1] > 0]
            print("%s %-7s %s" % ("ok " if not bad else "ERR", vid, text))
            for label, w, heard in bad:
                print("      %-5s %3.0f%%  heard: %r" % (label, w * 100, heard))
    print()
    for label, ws in totals.items():
        if ws:
            exact = sum(1 for w in ws if w == 0)
            print("%-5s word error rate %5.1f%%   exact %d of %d clips" % (
                label, 100.0 * sum(ws) / len(ws), exact, len(ws)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
