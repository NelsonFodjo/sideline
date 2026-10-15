# Demo video: script and shot list

Target **2:45**, never over 3:00 (the rule). English, public, **no music, no third-party trademarks** (no club crests,
broadcast footage, league or feed logos: team names in text are fine). Add captions: the product is for listeners who
cannot see a screen, so a video that cannot be followed without sound or without captions would undercut it.

The middle of the video is **live**: real questions, asked aloud, with the real wait and the real answer. Nothing is
scripted on the assistant's side. The answers below say what *kind* of sentence to expect, not its words, because the
data is live. If an answer is not what you want, do not edit it in: record that question again (the take is the demo).

## Before recording (20 minutes, the day of)

1. `make run`, then `make sim`. Confirm `make env` shows AWS keys set (model: Nova Pro, the default).
2. Open `http://127.0.0.1:8765/` in a clean browser window (no bookmarks bar, no other tabs). Zoom to 125%.
   Allow the microphone once. Press **Alt+D** once to confirm the Dev log opens, then close it.
3. **Pick two matches** an hour before: `make next-matches` lists what is coming, and the page answers "what's on today?":
   - **A live match** (for questions 1 to 3 and 6): anything in play on the day, any sport.
   - **A finished match from the last day** (for questions 4 and 5): ideally football with a penalty, so "was there a
     penalty" has something to say. Write down both team names and one player from the finished match.
4. **Warm up, then rehearse.** The first question after the server starts is slower (we measured 9 s for "follow" on a cold start, 2 to 3 s afterwards). Ask any question once off camera right before recording. Then rehearse all seven questions once each. Note any that miss and re-word them; do not change the product to suit the take.
5. Hide the `.env` file and any terminal that prints keys. Turn off notifications. Close anything with a logo.
6. Record the screen at 1080p with your own voice as narrator, microphone close, no music bed.
   Keep the browser's audio in the recording: the assistant's voice is part of the demo.

## The shots

| Time | On screen | Say (narration) |
|---|---|---|
| **0:00 to 0:15** | The simulator idle: blue eye, nothing else. | "A television match is a picture. The score sits in a corner; line-ups and cards flash on graphics nobody reads out. If you can't see the screen, you miss the match. A friend beside you would just tell you. Sideline is that friend." |
| **0:15 to 0:30** | Split: the terminal with the server log (`MCP endpoint: http://127.0.0.1:8765/mcp`), then back to the page. | "Sideline is an MCP server: thirty tools, live data, and a memory of what each listener has already heard. This page only simulates Alexa+, so you can talk to it. Everything you'll see is the MCP." |
| **0:30 to 1:55** | The simulator, full screen. **Live, seven questions** (next section). Pause 2 seconds after each answer before the next. | Narrate only in the gaps, in one short sentence each (given below). Stay silent while the assistant is thinking: the wait is the evidence. |
| **1:55 to 2:15** | Press **Alt+D**: the Dev log. Scroll the last two questions. | "Here is what happened behind each answer: which MCP tool ran, with what arguments, which model chose it, and how long each step took. The model is Amazon Nova Pro on Bedrock." |
| **2:15 to 2:30** | Terminal: `python3 scripts/check_with_sdk.py` (a virtualenv with `mcp` installed, already prepared). Show the last two lines. | "And it isn't tied to our page: the official MCP Python SDK connects, lists all thirty tools and calls them." |
| **2:30 to 2:45** | A plain text card (white on dark, no logos): the repository address, "52 offline test suites · 27-entry friction log · routing 77/79 on Nova Pro". | "Built on Amazon Bedrock, Polly and DynamoDB. The tests, the friction log and the limits are all in the repository. It isn't on real Alexa+ yet, because that tooling is partner-only; it is built to be hosted and connected when it is." |

Leave at least 5 seconds of margin: if the live section runs long, cut the SDK shot, not a question.

## The live section (0:30 to 1:55): seven questions

Ask each one out loud, hands off the keyboard. Say the team or player names you wrote down.

| # | Ask (about) | Expect (the kind of answer) | Gap line to narrate |
|---|---|---|---|
| 1 | "Follow *[team in the live match]*." | One sentence: who is playing, the score, the minute. The score on screen bumps into place. | "I just name a team. It finds the match." |
| 2 | "What did I miss?" (right away) | Either "nothing new" or a short catch-up of what happened since it last told me. | "It remembers what I've heard." |
| 3 | "What's the score?" about 30 seconds later, then "What did I miss?" again | The score, then only what is *new* since question 2: it does not repeat itself. | "Ask again later and it only tells me what's new. That memory lives on the server." |
| 4 | "Tell me more about *[player from the finished match]*." | Name, nationality, age, position and club, then an offer: "do you want his season or this match?" It does not invent titles. | "It says what it knows, and offers more." |
| 5 | "Was there a penalty in the *[finished match]*, and what were the stats?" | Who took it, the result and the minute, then a short stats run (possession, shots, corners, fouls). | "Straight facts, in an order you can follow by ear." |
| 6 | "My TV is about forty seconds behind." then "What's the score?" | It confirms the delay; the score it gives holds back anything your picture hasn't shown yet. | "It will not spoil a goal your TV hasn't shown yet." |
| 7 | "How is *[a made-up team, e.g. Zorbax United]* doing?" | A plain sentence that it can't find that team, with what to try. If anything goes wrong: "Sorry, an error occurred. Please try rephrasing your question for a better search, or try again later." | "When it can't help, it says so. It never guesses." |

Notes for the take:
- A model answer takes roughly **2 to 4 seconds** once warm (a plain score can be under a second, because those skip the model); after 6 seconds the page shows "Still working on it…". Do not cut it:
  show the deep-blue "thinking" eye and say nothing. If it exceeds 8 seconds, stop, check the terminal, and retake.
- Question 3 needs about 30 seconds of real match time between 2 and 3. Use the wait to narrate "the match is moving".
- If the live match ends mid-recording, swap in the other match; do not fake a clock.
- Question 6 also proves the guard: a total such as the stats table is held back for a delayed listener ("up to the
  second, so it could get ahead of your picture"). If you hear that sentence, it is working.
- Do not say, or put on a card, anything you have not seen: no number of users, no claim of testing with blind users
  beyond what the team will state first-hand, no claim of running on real Alexa+.

## After recording

1. Trim to under **2:55**. Add captions (auto-generate, then correct names and the model name).
2. Check the frames for keys, emails, account ids, club crests, logos: scrub or crop.
3. Upload as **public** (YouTube or Vimeo), no music, title "Sideline: a friend for the match, in your ear".
4. Put the link in the Devpost form, and in [HACKATHON.md](HACKATHON.md) ("Demo video"). Then replace "to be recorded".
5. Submit before **Friday 23 October 2026, 12:00 pm Pacific** (23:00 in Mauritius). Nothing can change after.

## If a live answer goes wrong on camera

Say so and retake; a faked take is worse than a second one. If the feed is down, record question 1 to 3 on a different
sport, or use `python3 scripts/ask.py` for the finished match. Never speed up or splice an answer so it looks faster
than it was: the latency numbers in the docs are measured, and the video should match them.
