#!/usr/bin/env python3
"""Head to head on the same clips: the speech-to-text models on Amazon Bedrock (Mistral Voxtral small and
mini, Nova 2 Sonic, Nova 2.5 Sonic). Groq's hosted Whisper was the benchmark they were measured against, and
was removed from the product when Voxtral matched it: the numbers are in docs/SPEECH.md and docs/FRICTION_LOG.md.

    python3 scripts/compare_stt.py

Needs AWS credentials (Polly speaks the clips; the AWS models listen) and, for Sonic, the Bedrock
streaming SDK (pip3 install aws-sdk-bedrock-runtime awscrt, Python 3.12+). `python3 scripts/compare_stt.py
voxtral` runs only the named contenders. Eight football phrases, three voices, each clean and with room
noise added (about 10 dB signal to noise). Every contender gets its production configuration: Sonic gets the match
vocabulary as a hint, Voxtral gets none (a chat model prints and answers from a list of names).

Scoring is forgiving about things the product does not care about (case,
punctuation, "half time" against "halftime") and strict about the words that
matter, and it reports names separately because a wrong name is a wrong answer.
Synthetic voices are cleaner than people; treat the numbers as a comparison
between providers, not as accuracy a listener will see.
"""

import os
import random
import re
import struct
import sys
import time
import unicodedata

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sideline  # noqa: E402,F401  (loads .env)
from sideline import voice  # noqa: E402
from verify_stt import NAMES, PHRASES, VOICES, speak  # noqa: E402

NAME_TOKENS = ["odegaard", "alderweireld", "saka", "bellerin", "hector", "martin",
               "bukayo", "toby"]


def norm(s):
    s = unicodedata.normalize("NFKD", s.lower().replace("ø", "o"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[-']", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\bhalf time\b", "halftime", s)
    s = re.sub(r"\bkick off\b", "kickoff", s)
    s = re.sub(r"\bhead to head\b", "headtohead", s)
    return s.split()


def wer(ref, hyp):
    r, h = norm(ref), norm(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / float(max(1, len(r)))


def names_ok(ref, hyp):
    """(names in the phrase, names heard exactly)."""
    want = [t for t in norm(ref) if t in NAME_TOKENS]
    got = set(norm(hyp))
    return len(want), sum(1 for t in want if t in got)


def with_noise(pcm, snr_db=10.0, seed=7):
    """Add white noise at a given signal to noise ratio: a crude television-room."""
    n = len(pcm) // 2
    samples = struct.unpack("<%dh" % n, pcm[:n * 2])
    rms = (sum(s * s for s in samples) / float(n)) ** 0.5
    sigma = rms / (10 ** (snr_db / 20.0))
    rng = random.Random(seed)
    out = [max(-32768, min(32767, int(s + rng.gauss(0, sigma)))) for s in samples]
    return struct.pack("<%dh" % n, *out)


def main():
    if not voice._have_aws_credentials():
        print("set AWS credentials to compare")
        return 1
    hint = voice._BASE_HINT + " " + NAMES
    def sonic(model):
        def run(pcm):
            real, voice.SONIC_MODEL = voice.SONIC_MODEL, model
            try:
                return voice._transcribe_sonic(pcm, hint)
            finally:
                voice.SONIC_MODEL = real
        return run

    contenders = [("voxtral", lambda pcm: voice._transcribe_voxtral(pcm, hint)),
                  ("vox-mini", lambda pcm: voice._transcribe_voxtral(pcm, hint, "mistral.voxtral-mini-3b-2507")),
                  ("sonic2", sonic("amazon.nova-2-sonic-v1:0")),
                  ("sonic2.5", sonic("amazon.nova-2-5-sonic"))]
    if not voice.HAVE_SONIC:
        contenders = [c for c in contenders if not c[0].startswith("sonic")]
        print("(Nova Sonic skipped: pip3 install aws-sdk-bedrock-runtime awscrt, Python 3.12+)")
    wanted = sys.argv[1:]
    providers = [c for c in contenders if not wanted or c[0] in wanted]
    stats = dict((p, {"clean": [], "noisy": [], "t": [], "fail": 0,
                      "names": [0, 0]}) for p, _ in providers)
    misses = []
    n = 0
    for text in PHRASES:
        for vid, _ in VOICES:
            clean = speak(text, vid)
            for cond, pcm in (("clean", clean), ("noisy", with_noise(clean))):
                n += 1
                row = []
                for name, fn in providers:
                    t0 = time.time()
                    out = fn(pcm)
                    dt = time.time() - t0
                    heard = out["text"] if out else ""
                    s = stats[name]
                    if not out:
                        s["fail"] += 1
                    w = wer(text, heard)
                    s[cond].append(w)
                    s["t"].append(dt)
                    want, got = names_ok(text, heard)
                    s["names"][0] += want
                    s["names"][1] += got
                    row.append((name, w, heard))
                if any(w > 0 for _, w, _ in row):
                    misses.append((cond, vid, text, row))
                print("\r%d clips" % n, end="")
                sys.stdout.flush()
    print("\n")
    print("%-9s %-10s %-10s %-12s %-16s %-9s %s" % (
        "", "WER clean", "WER noisy", "exact (all)", "names right", "avg time", "failed"))
    for name, _ in providers:
        s = stats[name]
        allw = s["clean"] + s["noisy"]
        print("%-9s %-10s %-10s %-12s %-16s %-9s %d" % (
            name,
            "%.1f%%" % (100 * sum(s["clean"]) / len(s["clean"])),
            "%.1f%%" % (100 * sum(s["noisy"]) / len(s["noisy"])),
            "%d of %d" % (sum(1 for w in allw if w == 0), len(allw)),
            "%d of %d" % (s["names"][1], s["names"][0]),
            "%.1fs" % (sum(s["t"]) / len(s["t"])), s["fail"]))
    print("\nwhere either one was wrong (after forgiving case, punctuation, 'halftime'):")
    for cond, vid, text, row in misses:
        print("  [%s, %s] %s" % (cond, vid, text))
        for name, w, heard in row:
            if w > 0:
                print("      %-9s %3.0f%%  %r" % (name, w * 100, heard))
    return 0


if __name__ == "__main__":
    sys.exit(main())
