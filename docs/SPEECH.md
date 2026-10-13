# Speech in

How a listener's voice becomes text, which model does it, and why. Measured on 2026-10-13, not assumed.

**Everything runs inside the AWS account.** The listener's audio goes to a model on Amazon Bedrock and nowhere else
(live captions aside, see below). That was not where we started: a third-party service won the first comparison, and
this page is the story of how an AWS model caught it.

## The decision

| Order | Model | When it is used |
|---|---|---|
| 1 | **Mistral Voxtral Small** (`mistral.voxtral-small-24b-2507`), on Bedrock, through Converse | AWS credentials work. About 0.8 s per clip |
| 2 | **Amazon Nova 2 Sonic** (Bedrock bidirectional streaming) | Voxtral failed for that clip, and the streaming SDK is installed (Python 3.12+). About 3.5 s |
| 3 | the browser's own recognition | nothing above is available. The least accurate |

Amazon Transcribe is not used: the account this was built on returned `SubscriptionRequiredException` for it
(see [FL-08](FRICTION_LOG.md)).

`SIDELINE_STT=auto` (the default) walks that list. **A clip that one model fails goes to the next**, so a throttle or a
blip never leaves a listener unheard; a clip that a model heard nothing in is *not* retried (silence is an answer). A
model that fails in a way retrying cannot fix (access denied) is dropped for the rest of the run. Naming one
(`SIDELINE_STT=sonic`) uses it alone and never silently swaps it for another.

## How we got here: three rounds

**Round 1: Nova Sonic against a third party (Groq's hosted Whisper), 48 clips.** Groq won clearly, so it led, with
Sonic as the "stays in AWS" fallback. Word error 0.4% clean and 3.7% noisy against Sonic's 0.8% and 8.5%, and 1.1 s a clip
against 4.2 s. That meant the listener's audio left AWS whenever a key was set, which for a product whose listeners may
be blind is a real cost, and the one part of the build that did not run on AWS.

**Round 2: can a model *inside* AWS match it?** A look at what Bedrock offers for speech found Mistral's Voxtral (audio in,
text out through the ordinary Converse API) and a newer Nova Sonic. We had tried Voxtral once and **rejected it**: on four
phrases it answered "What's the score?" with an invented "The score is 2-1." and refused another. Invented text is the
failure this product cannot afford. This time we found out why, instead of giving up:

- Voxtral is a chat model. Put the instruction *before* the audio and it answers what it hears; put the **audio first** and
  the instruction after it, and it transcribes.   once wrote "Alright, so I'm going to ask you a question" over and over.)
- A **system message is refused** alongside audio (`ValidationException`), so the instruction goes in the user turn.
- The small model is reliable and the **mini model is not**: on the full run it answered questions ("That goal was scored by
  Martin Ødegaard for Arsenal.") and printed the names from the vocabulary hint when given noise.
- **Giving it a vocabulary made it worse.** Every other recogniser takes a list of names to spell right, so we sent one. This
  chat model treats it as content: on twelve clips (questions, statements, "The first one."), with the names in the prompt it
  printed the list for "The first one." and, in one wording, answered "What's the score?" with "The score is Arsenal 1...".
  With no names, 0 of 12 failed. So **no vocabulary is sent to Voxtral**; misheard names are repaired after the fact
  (`resolve.py`), and the 48-clip run was repeated without the names (below).
- A reply with far more words than the clip could hold is not a transcript, so it is dropped, which turns a model that talks
  about the audio into a clip that falls back to Sonic.

**Round 3: the same 48 clips, head to head** ([scripts/compare_stt.py](../scripts/compare_stt.py)). Polly speaks 8
football phrases (names such as Ødegaard, Alderweireld, Saka and Bellerín) in 3 voices; each clip is run clean and again
with white noise at about 10 dB signal to noise, a crude room with a television on. Every contender got the production
configuration, the match vocabulary as a hint. Scoring forgives case, punctuation and "halftime" against "half time",
and counts names separately.

```
              WER clean  WER noisy  exact (all)  names right   avg time  failed
groq          0.4%       3.7%       43 of 48     44 of 48      1.4 s     0       (third party: the benchmark)
voxtral       0.0%       1.4%       47 of 48     48 of 48      0.8 s     0       (AWS, no vocabulary: what ships)
voxtral+names 1.3%       2.6%       41 of 48     48 of 48      1.2 s     0       (AWS, names in the prompt: first run)
vox-mini      78.8%      83.3%      7 of 48      9 of 48       0.7 s     21      (AWS, no vocabulary: eliminated)
sonic 2       0.8%       8.5%       39 of 48     40 of 48      4.2 s     0       (AWS, round 1)
```

The first Voxtral run (with names) and the shipped one (without) are two runs of the same 48 clips. Mini was run both ways: with
names 24.6% and 39.1% error and 4 failed clips; without, 21 failed clips (the length guard dropped replies that were answers).

| | Groq (third party) | Voxtral Small (AWS) |
|---|---|---|
| Word error, clean | 0.4% | **0.0%** |
| Word error, noisy | 3.7% | **1.4%** |
| Clips exact, of 48 | 43 | **47** |
| Names right, of 48 | 44 | **48** |
| Average time, per clip | 1.4 s | **0.8 s** |
| Where the audio goes | **outside AWS** | stays in your AWS account |

On this set Voxtral, as shipped, is ahead on every measure, and it **got every name right**, which is the thing that matters
here, because a wrong name is a wrong answer. We read that as "at least level", not "better": 48 clips, one run, synthetic
speech. The first run (with the names in the prompt) had Groq a little ahead on clean speech, which is why the comparison
is described as level. Either way it met the condition for removing the third party, so Groq was removed and Voxtral leads.

**Eliminated, by the rule "one error or being slow is enough":**

- **Voxtral Mini:** answers the question it hears instead of writing it down, and fails clips (4 with the names, 21 without).
  Out.
- **Nova 2 Sonic:** 4.2 s a clip in the full round-1 run, five times slower than Voxtral, and 8.5% error in noise. Kept
  only as the fallback.
- **Nova 2.5 Sonic** (`amazon.nova-2-5-sonic`): a six-clip sample (one voice, clean and noisy) gave 3.4 s and 8% error
  against Nova 2's 3.7 s and 8%: slightly quicker, no more accurate, still about four times slower than Voxtral. Out.

### What this does and does not show

- **Synthetic speech.** Polly is cleaner and more regular than a person, and the noise is white noise, not a crowd or
  commentary. It compares the models; it does **not** predict accuracy for a real listener.
- **Small sample.** 48 clip-conditions, 8 phrases, one run each, no variance reported. Voxtral and Groq are level within
  what this can tell apart, not proven equal.
- **The Nova Sonic 2.5 figures are a six-clip sample.** The full 48-clip run never completed for either Sonic model on
  this machine's second attempt: the first was void (the SDK's CRT component would not import with `awscrt` 0.26.1 on
  Python 3.14; `awscrt` 0.37 fixed it) and the second was stopped as too long. Nova 2's full-run figures are from round 1.
- **Sonic's time is inflated by our design.** It decides a speaker has finished by hearing silence, so we stream 2 s of
  silence after each clip. A shorter pad would cut it; it was not tuned.
- **The remaining risk with Voxtral is that it is a chat model.** The length guard stops one that talks; it cannot catch
  a short, wrong reply, such as the invented score we saw in the first attempt. None appeared in 48 clips including six of
  "What's the score?", but that is evidence, not a guarantee. Sonic is the fallback, and `SIDELINE_STT=sonic` pins it.
- **The vocabulary hint is not sent to Voxtral** (see round 2). Sonic still gets it; whether it helps Sonic was **not
  measured** separately. The one Voxtral miss in 48 was a name in noise.
- **Browser recognition was not measured here.** It cannot be driven from a script. Say the same phrases into the
  simulator to compare.

## What it costs, and what you give up

- **Nothing leaves AWS.** Voxtral and Sonic run on Bedrock in your account, so speech in counts for the AWS Builder entry and
  needs no third-party key or terms. Sideline stores no audio. See [ACCESSIBILITY.md](ACCESSIBILITY.md).
- **Live captions are the one exception**, and are switchable: while you speak the page also runs the browser's recognition
  to type interim words, which sends that audio to the browser's vendor (Chrome and Edge send it to theirs).
  `SIDELINE_LIVE_CAPTION=off` keeps the audio with Bedrock only, and nothing types until the clip ends.
- **Voxtral is a Bedrock model you must have access to** in your region (`us-east-1` here), and every call is billed as
  input and output tokens. They are logged with the rest (`make log-report`, source `speech`).

## Setup

```bash
pip3 install boto3                                 # all that Voxtral needs
pip3 install aws-sdk-bedrock-runtime awscrt        # optional: Nova Sonic, the fallback (Python 3.12+)
```

Restart; the startup log says `voice: in=voxtral out=polly (Amy)`. Then:

```bash
make stt-check        # one model, with and without the vocabulary hint
make compare-stt      # the AWS models head to head, clean and noisy (ARGS names contenders: voxtral sonic2)
make aws-check        # includes a real round trip through the active model
```

Both use IAM credentials resolved through boto3 (the access key pair, or an instance role with
`SIDELINE_BEDROCK=on`).

## Speed, and typing while you talk

Measured on 2026-10-13, from the moment you stop talking to the first audio:

| Stage | Before | After |
|---|---|---|
| Waiting to be sure you have stopped | 0.85 s | 0.70 s (`SILENCE_MS` in the simulator) |
| Speech recognition (Groq at the time; Voxtral is about 1.2 s) | 0.8 s | 0.8 s |
| Nova agent (one or more tool calls) | 0.8 to 2.8 s | unchanged: the largest remaining cost, and the first turn is the slowest |
| Polly speech (audio, then word marks) | 1.8 s | about 0.5 s: the two calls now run in parallel, and Polly is warmed at startup |

That is roughly 4.5 to 6.5 s before and 3.5 to 5 s after. The agent is what is
left; skipping it for plain questions ("what's the score") would cut most of the
rest and has not been done.

**Typing as you speak.** Server recognition (Voxtral, Sonic) returns text only after
the clip ends, so nothing could type while you talked, which browser recognition
does. The page now runs the browser's recognition on the side **purely to show
interim words**, then replaces them with the server's more accurate transcript.
Cost: that audio also reaches the browser vendor, as it did before. Set
`SIDELINE_LIVE_CAPTION=off` to keep the audio with the chosen provider only (then
nothing types until the clip ends). Not available in Firefox, which has no
browser recognition. This was verified by unit tests and by reading the code, but
**not in a browser by me**: try it in Chrome.

## Understanding what you meant

Two things make the recogniser's literal words the wrong thing to act on, and
both are handled in [sideline/resolve.py](../sideline/resolve.py).

**A choice was just offered.** "I can see more than one Arsenal match: Tottenham
Hotspur against Arsenal, or Arsenal against Tottenham?" You answer in your own
accent, "tottenham hot spur", "gamma osaka", "pohan steelers". The server
remembers what it just offered you (for two minutes, and until you answer) and
snaps a short answer to the option you were closest to, by spelling and by a
rough sound code, ignoring spaces ("shang high" is "Shanghai"). "The first one",
"second", "number two" pick by position. It also primes the recogniser: the
offered options go to the front of the recogniser's vocabulary for your next clip.

It is deliberately cautious, because a wrong guess spoken back as fact is worse
than asking again and you cannot see the screen to catch it:

- an answer that fits two options about equally ("arsenal" when both matches
  have Arsenal) is **not** guessed, and the agent asks again;
- a long sentence is not an answer: it is a new question and is left alone;
- when it does change what you said, the page shows what it understood
  (`understood` in the agent response), so a wrong snap is visible;
- when the answer maps to a specific match, the model is told its `fixture_id`.
  Without that it called `follow_match` with just "Tottenham", which is
  ambiguous again, and asked a second time (seen in a real run). With it, three
  real runs out of three followed the right match.

**A name from the match was misheard.** "Bukaiyo Saka" is repaired to "Bukayo
Saka" when it is very close to a name in the match you follow; short and common
words (score, goal, half) are never touched however they sound. When the agent
asks an open question with no list ("which team?"), the likely answers are the
teams playing today. Names come from our own event log, so this costs no feed
requests.

Tested on mispronunciations of real names (`tests/test_resolve.py`); **not
tested with real voices**, and the thresholds were tuned on typed approximations
of mispronunciation, not recordings of accents.

## Keyboard and other noise

The simulator used to treat any sound above a fixed level as speech, and a key
press is loud for a moment. Two layers now stop it:

- **In the page**: a frame counts as speech only if it is louder than this
  room's own (continuously learned) noise, is not click-like (a click has much of
  its energy above 5 kHz, speech little), and holds for several frames in a row.
  A keystroke lasts under 30 ms, a mug on the desk under 100; a word is far
  longer. Barge-in uses the same rule, measured against the speaker's own leakage into the microphone, so typing
  while it talks does not cut the answer off, and speaking over it does. What had been said when you cut in is
  sent with your next question, so "and him?" is read as a follow-up. The logic runs under Node in `tests/test_simulator.py`.
- **On the server**: before a clip goes to any provider it must contain at least
  160 ms of *sustained* sound. A clip of clicks is dropped and costs no request
  (a recogniser turns clicks into "Thank you."). Speech with typing in the background
  is kept.
- **Noise is never text.** Recognisers describe non-speech in brackets: Chrome's live caption wrote "[SOUND]" on screen, and
  a speech model can write "[inaudible]". That describes a sound; nobody said it. `[...]`, `(...)`, `{...}`, `*cough*`, `<...>`
  and music notes are stripped everywhere text can reach the screen or the agent: the live caption, the browser's recognition,
  the server's transcript (`voice.only_words`) and the page (`justWords`). If nothing but a label is left, nothing is shown
  and nothing is sent, and a clip heard only as "[SOUND]" counts as heard nothing. Pinned by `tests/test_voice.py` and, for the
  page's real function under Node, `tests/test_simulator.py`.
- **The live caption**: the browser's own recognition will "hear" words in a fan, so its text is shown only
  once the page's detector agrees someone is speaking.
- **A recogniser reading its own vocabulary**: given noise and a vocabulary, a recogniser tends to print the names, which
  once produced two team names nobody had said (Whisper did, and Voxtral Mini does). A transcript of two or more words made only
  of names from the hint, with no question words, is discarded unless the listener was just offered a choice (then a bare
  name is the answer), and one bare name is always kept. Voxtral's reply is also dropped if it has more words than the
  clip could hold. All of it is pinned in `tests/test_voice.py`.

- **Cutting in is a whole word, not a noise.** While it speaks, the page measures its own voice leaking into the
  microphone for half a second, then needs about 360 ms of speech-like sound (louder than the room by a wide margin
  and than that leakage, not click-like) before it stops. At the first sign of sound the voice is only turned down,
  and it comes straight back if the sound was a cough or a door. The last 0.8 s are kept, so the clip starts at the
  beginning of your word and the first syllable is not lost to the time it took to decide.

Limits, stated plainly: this is a detector tuned on synthetic frames, **not tried
in a real browser with a real keyboard**; a constant hum (a fan) is learned over
a few seconds rather than rejected at once; and typing very close to the
microphone while you are silent but *then* speaking is the hardest case.

## Speech out: a voice that flows

The first voice (Polly's neural Amy) read every sentence alike, which is what "generic" sounds like over a long answer.
Polly's **generative** voices vary pace and stress as a person does, so that is the default (`SIDELINE_POLLY_ENGINE`).
Two problems came with it, and both are handled in `voice.synthesize`:

- **No word timings.** The page highlights each word as it is spoken, and the generative engine cannot return the marks.
  The marks come from the neural voice for the same sentence, one per word, and are fitted to the generative audio's
  exact length (read from the MP3's own frame headers, `mp3_seconds`). They are positioned in the text as written, so
  nothing shifts when the spoken form differs ("U21" is said "under 21").
- **Flow.** Made a sentence at a time, each sentence started afresh and the joins sounded like a list. So a short answer is
  made in one call, and the voice keeps its pace and stress across its sentences. Measured against the real service,
  the word highlighting stays within about half a second. An answer longer than about 150 characters is cut at sentence ends into pieces of
  two or three sentences, made at once: that keeps a long preview ready in about 2 to 3 s, where one piece took 4.6 s.

**How things are said.** The page highlights words one for one, so a spoken form must stay one token. `speakable` maps "U21" to
"under-21" and "Alexa+" to "Alexa-plus" (Polly would drop the plus). "MCP" is left alone: Polly already says it letter by letter, and
spelling it "M-C-P" made the intro a second slower (4.3 s against 5.3 s for the same sentence).

If the generative engine is not available for the voice or region, the answer falls back to neural with its own exact
timings, and says so in the log. Pinned in `tests/test_voice.py` with a fake Polly; whether it *sounds* better is for your
ears: `SIDELINE_POLLY_ENGINE=neural` is the one-line way back, and `SIDELINE_POLLY_VOICE` accepts any generative voice
(en-GB: Amy, Brian; en-US: Matthew, Ruth, Stephen, Joanna, Danielle, Salli, Tiffany).

## Getting names right

Names are where recognisers fail, so three layers work on them. The hint carries the teams on today (live ones
first), each also in plain letters ("Sønderjyske" and "Sonderjyske"). A name heard a little off is repaired inside
the sentence from those teams and the followed match's players, only when it is very close ("Midtylland" becomes
"Midtjylland"; ordinary words are never touched). And a team the repair would not trust is still found by the tools
by spelling and sound, or offered back: "I couldn't find asana. Did you mean Arsenal against Lille?" Nicknames
(Spurs, Man City, Copenhagen) are a short table. `scripts/compare_stt.py` is how to re-measure the recogniser.

## How the vocabulary hint works

Sideline builds a vocabulary from the teams and players of the match the listener follows (from our own event log, so it costs
no feed requests), the teams on today, what the listener was just offered, and a short list of the words they use (score,
line-up, referee, VAR, kick-off). **Nova Sonic gets it in its system prompt. Voxtral does not**: a chat model treats a list of
names as content to print or answer from (round 2), and it did better without. The vocabulary still has two jobs: it
tells us when a transcript is only the recogniser reading names back (`echoes_hint`), and the names it holds are what the
repair step in `resolve.py` snaps a misheard name to.

## Tried and rejected

**Groq's hosted Whisper** (`whisper-large-v3-turbo`) was the benchmark and led until Voxtral matched it: see the three
rounds above. Removed, with its key, its request code and its tests, so the product has no third-party service in the
voice path. It remains in the git history, and the numbers it set are above.

**Voxtral Mini, Nova 2 Sonic and Nova 2.5 Sonic** as the first choice: see "Eliminated" above.

**Mistral Voxtral, first attempt.** Rejected for inventing a score and refusing a clip. Revisited because Bedrock lists it
for speech, and found to work once the audio goes first and the instruction is in the user turn. A rejection can be the
fault of how a model was asked.

## Integration notes (Nova Sonic)

Found while building it; useful to anyone else doing the same.

- It is **not in boto3**. The bidirectional streaming API needs the separate
  `aws-sdk-bedrock-runtime` package (Python 3.12+) and `awscrt`; the default
  HTTP transport does not support duplex streaming and says so clearly.
- `AsyncBedrockRuntimeConfig` cannot be constructed directly: use
  `await AsyncBedrockRuntimeConfig.resolve(...)`, with `transport=`, not
  `http_client=`.
- Closing the prompt straight after the audio returns nothing. It waits to
  hear silence, so a trailing 2 s of silence is sent and the reply is awaited.
- Sonic always tries to answer. We tell it to say "OK" and stop reading at its
  first reply, so a transcript costs the audio in plus a token or two out.
- Awaiting `input_stream.close()` on a finished stream can hang, and the
  caller's timeout then waits on it forever. Cleanup is bounded to 2 s.
