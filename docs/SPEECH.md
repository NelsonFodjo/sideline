# Speech in

How a listener's voice becomes text, which provider does it, and why. Measured
on 2026-10-13, not assumed.

## The decision

| Order | Provider | When it is used |
|---|---|---|
| 1 | **Groq Whisper** (`whisper-large-v3-turbo`) | `GROQ_API_KEY` is set. A third party outside AWS |
| 2 | **Amazon Nova 2 Sonic** (Bedrock) | the Bedrock streaming SDK is installed and AWS credentials work. Stays in the AWS account |
| 3 | the browser's own recognition | nothing above is available. The least accurate |

Amazon Transcribe is not used: the account this was built on returned `SubscriptionRequiredException` for it
(see [FL-08](FRICTION_LOG.md)).

`SIDELINE_STT=auto` (the default) walks that list. **A clip that one provider
fails goes to the next**, so a rate limit or a blip never leaves a listener
unheard; a clip that a provider heard nothing in is *not* retried (silence is
an answer). A provider that fails in a way retrying cannot fix (a bad key,
access denied) is dropped for the rest of the run. Naming a
provider (`SIDELINE_STT=sonic`) uses that one alone and never silently swaps
it for another, because a choice about where a voice goes should be respected.

With **no Groq key nothing leaves AWS** (apart from live captions, below): Sonic is first. That is also
what anyone gets who has not added a key.

## Why Groq first: the head-to-head

`make compare-stt` ([scripts/compare_stt.py](../scripts/compare_stt.py)). Polly
speaks 8 football phrases (names such as Ødegaard, Alderweireld, Saka and
Bellerín) in 3 voices; each clip is run clean and again with white noise added
at about 10 dB signal to noise, a crude room with a television on. Both
providers got the production configuration, the match vocabulary as a hint.
Scoring forgives case, punctuation and "halftime" against "half time", and
counts names separately.

```
        WER clean  WER noisy  exact (all)  names right      avg time  failed
sonic   0.8%       8.5%       39 of 48     40 of 48         4.2s      0
groq    0.4%       3.7%       43 of 48     44 of 48         1.1s      0
where either one was wrong (after forgiving case, punctuation, 'halftime'):
  [noisy, Joanna] What's the score?
      sonic  50%  "what's this for"
  [noisy, Amy] Who is refereeing, and what did I miss since half time?
      sonic  10%  "who's refereeing and what did i miss since halftime"
  [noisy, Amy] Who is Martin Ødegaard?
      sonic  25%  'who is martin odegard?'
      groq   25%  'who was Martin Odegaard.'
  [noisy, Brian] Who is Martin Ødegaard?
      sonic  25%  'who is martin oddegaard'
  [clean, Amy] Has Toby Alderweireld been booked?
      sonic  20%  'has toby oldevaereld been booked?'
  [noisy, Amy] Has Toby Alderweireld been booked?
      sonic  20%  'has toby oldevaereld been booked?'
  [noisy, Amy] Kick-off just went.
      sonic  33%  'kiko just went'
      groq   33%  'Kiko, just went.'
  [noisy, Amy] What was the VAR decision on Bukayo Saka's goal?
      groq   10%  "What was the VAR decision on Bukaiyo Saka's goal?"
  [noisy, Brian] What was the VAR decision on Bukayo Saka's goal?
      sonic  20%  "what was the var decision on bocayo saca's goal"
  [clean, Joanna] What was the VAR decision on Bukayo Saka's goal?
      groq   10%  "What was the VAR decision on Bukaiho Saka's goal?"
  [noisy, Joanna] What was the VAR decision on Bukayo Saka's goal?
      sonic  20%  "what was the var decision on bajaj sakkal's goal?"
      groq   20%  "What was the VAR decision on Bukai Osaqa's goal?"
```

| | Groq | Nova Sonic |
|---|---|---|
| Word error, clean | **0.4%** | 0.8% |
| Word error, noisy | **3.7%** | 8.5% |
| Clips exact, of 48 | **43** | 39 |
| Names right, of 48 | **44** | 40 |
| Average time, per clip | **1.1 s** | 4.2 s |
| Failures | 0 | 0 |
| Where the audio goes | **Groq** | stays in your AWS account |
| Needs | a key; free tier, about 20 requests a minute | the Bedrock streaming SDK, Python 3.12+ |

Groq was more accurate and about four times faster, so with a key it leads.
Sonic's clean accuracy is close (0.8% against 0.4%); it falls behind in noise.

### What this does and does not show

- **Synthetic speech.** Polly is cleaner and more regular than a person, and the
  noise is white noise, not a crowd or commentary. It compares the two
  providers; it does **not** predict accuracy for a real listener.
- **Small sample.** 48 clip-conditions, 8 phrases. The gap in noise is four
  clips (43 against 39 exact). Directionally consistent, not a precise rate.
- **Sonic's time is inflated by our design.** It decides a speaker has finished
  by hearing silence, so we stream 2 s of silence after each clip. Groq has no
  such wait. A shorter pad would cut Sonic's time; it was not tuned.
- **One run each.** No repeats, so no variance is reported.
- **Most of the errors are names.** Both mishear Saka and Alderweireld in noise
  ("Bukaiyo", "oldevaereld"). Whether the vocabulary hint helps was **not
  measured**: the head-to-head always used it, and a partial plain-versus-hint
  run on Sonic (one phrase, three voices) heard identical text either way.
- **Browser recognition was not measured here.** It cannot be driven from a
  script. Say the same phrases into the simulator to compare.

## What it costs, and what you give up

- **Groq is a third party: the listener's audio leaves AWS.** For a product
  whose listeners may be blind, that is a real cost, and a person should be told
  where their voice goes. It is never on unless a key is configured. Sideline
  stores no audio. See [ACCESSIBILITY.md](ACCESSIBILITY.md).
- **Groq's terms were not read, and its limits are from community sources.**
  The hackathon requires authorisation to use any third-party service. Reported
  free-tier limits are about 20 requests a minute and 2,000 a day; check Groq's
  own page. The comparison paced Groq to stay under them.
- **Sonic is an AWS service.** It runs on Bedrock in your account, so it counts
  for the AWS Builder entry; Groq does not.

## Setup

```bash
# Groq (best accuracy): a free key from console.groq.com, then in .env
GROQ_API_KEY=...

# Nova Sonic (stays in AWS; the automatic fallback). Python 3.12 or newer:
pip3 install aws-sdk-bedrock-runtime awscrt
```

Restart; the startup log says `voice: in=groq out=polly (Amy, neural)`. Then:

```bash
make stt-check        # one provider, with and without the vocabulary hint
make compare-stt      # Sonic against Groq, clean and noisy (needs both)
make aws-check        # includes a real round trip through the active provider
```

Nova Sonic uses IAM credentials resolved through boto3 (environment, profile,
container or instance role). A Bedrock API key on its own is not enough.

## Speed, and typing while you talk

Measured on 2026-10-13, from the moment you stop talking to the first audio:

| Stage | Before | After |
|---|---|---|
| Waiting to be sure you have stopped | 0.85 s | 0.70 s (`SILENCE_MS` in the simulator) |
| Groq transcription | 0.8 s | 0.8 s |
| Nova agent (one or more tool calls) | 0.8 to 2.8 s | unchanged: the largest remaining cost, and the first turn is the slowest |
| Polly speech (audio, then word marks) | 1.8 s | about 0.5 s: the two calls now run in parallel, and Polly is warmed at startup |

That is roughly 4.5 to 6.5 s before and 3.5 to 5 s after. The agent is what is
left; skipping it for plain questions ("what's the score") would cut most of the
rest and has not been done.

**Typing as you speak.** Server recognition (Groq, Sonic) returns text only after
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
offered options go to the front of Groq's vocabulary prompt for your next clip.

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
  (Whisper turns clicks into "Thank you."). Speech with typing in the background
  is kept.
- **The live caption**: the browser's own recognition will "hear" words in a fan, so its text is shown only
  once the page's detector agrees someone is speaking.
- **Whisper reading its own hint**: given noise and a prompt, Whisper tends to print the prompt, which once
  produced two team names nobody had said. Two guards: segments Whisper itself rates as probably silence and
  low confidence are dropped (`verbose_json`), and a transcript made only of names from the hint, with no
  question words, is discarded unless the listener was just offered a choice (then a bare name is the answer).
  Both are pinned in `tests/test_voice.py`.

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

Whisper takes a `prompt` that biases it towards given spellings. Sideline sends
the teams and players of the match the listener follows (from our own event
log, so it costs no feed requests) plus a short list of the words they use
(score, line-up, referee, VAR, kick-off). Sonic gets the same names in its
system prompt. Where the hint is not available the base phrases are sent.

## Tried and rejected

**Mistral Voxtral on Bedrock.** It accepts audio through the Converse API, but
it is a chat model, not a transcriber: on four phrases Voxtral Small answered
"What's the score?" with an invented "The score is 2-1.", refused another, and
got two right; Voxtral Mini was worse. Invented text is the failure this product
cannot afford.

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
