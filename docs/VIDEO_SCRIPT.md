# Demo video: script and shot list

The full guide, with screenshots, is [VIDEO_GUIDE.pdf](VIDEO_GUIDE.pdf) (source: [video/guide.html](video/guide.html)). The prompt
that generates the explainer animation is [video/ANIMATION_PROMPT.md](video/ANIMATION_PROMPT.md). Screenshots are in
[video/screenshots/](video/screenshots/). This page is the short version.

Target **2:45**, never over 3:00 (the rule). English, public, **no music, no third-party trademarks** (no club crests,
broadcast footage, league or feed logos: team names in text are fine). Add captions: the product is for listeners who
cannot see a screen, so a video that cannot be followed without sound or without captions would undercut it.

## The problem, as the video tells it

Not only blind and low-vision fans. **Anyone who wants a match now, without opening an app, searching or typing**: a driver, a
cook with wet hands, someone in a meeting, someone who arrived late and wants to know what they missed. For a blind fan,
asking is not a shortcut, it is the only way in; that is who it is built for first. Open on the everyday moment, arrive at
the people who need it most. Do not quote a statistic that is not in the repository.

## The shots

| Time | On screen | Say |
|---|---|---|
| **0:00 to 0:20** | Three quick cuts (hands in a kitchen, a car dashboard, a white cane), then the idle eye. | "You want the score. So you stop what you're doing, unlock your phone, open an app, search, scroll. Or you just ask. If you can't see a screen, asking isn't a shortcut, it's the only way in. Sideline is the friend who just tells you." |
| **0:20 to 0:32** | Terminal: `MCP endpoint: http://127.0.0.1:8765/mcp`, then the page. | "Sideline is an MCP server: thirty tools, live data, and a memory of what each listener has heard. This page only simulates Alexa+ so you can talk to it. Everything you see is the MCP." |
| **0:32 to 1:20** | **Football, live voice** (below). | One short sentence in each gap. Stay silent while she thinks. |
| **1:20 to 1:48** | **"Any game" montage**: Knicks, Broncos, then hockey or baseball, then a basketball line-up. A small label types the sport; the clock changes its words (`Q4`, `Final`, `P2`). | "Same server. Different game. Basketball counts in quarters, hockey in periods, baseball in innings. We didn't build five apps: the tools and the screen follow the sport." |
| **1:48 to 2:16** | The explainer animation. | Its own narration (in the prompt file). |
| **2:16 to 2:30** | Alt+D: the Dev log, last answer. | "Every answer is traceable: which tool, which arguments, how long, how many feed requests." |
| **2:30 to 2:48** | Plain card: the repository address, "61 offline test suites, 28-entry friction log, routing 77/79 on Nova Pro", then "Amazon Bedrock, Amazon Polly, Amazon DynamoDB". | "Built on Amazon Bedrock, Polly and DynamoDB. The tests, the friction log and the limits are in the repository. It isn't on real Alexa+ yet, because that tooling is partner-only; it is built to be hosted and connected when it is." |

Leave 5 seconds of slack. If you run long, cut the Dev log or part of the montage, never a football question.

## Before recording (20 minutes, the day of)

1. `lsof -iTCP:8765 -sTCP:LISTEN` should print nothing. Then `make run`, then `make sim`. Confirm `make env` shows AWS keys set (model: Nova Pro).
2. Open `http://127.0.0.1:8765/` in a clean browser window (no bookmarks bar, one tab). Zoom to 125%. Allow the microphone once.
   Press **Alt+D** to confirm the Dev log opens, then close it. Settings stay at their defaults.
3. **Pick the matches** an hour before: `make next-matches` lists what is coming; the page answers "what's on today?":
   - **A football match** from the last day (safest), or one in play. Write down both team names and two players.
   - **One match each** in basketball, American football and hockey or baseball (`make next-matches` shows them).
4. **Warm up, then rehearse.** The first question after the server starts is slower. Ask one question off camera, then rehearse every
   question once. Re-word any that miss; do not change the product to suit the take.
5. Hide `.env` and any terminal that prints keys. Turn off notifications. Close anything with a logo.
6. Record the screen at 1080p with your own voice as narrator, microphone close, no music. Keep the browser's audio.

## The live football section (0:32 to 1:20)

Ask each question out loud, hands off the keyboard. The answers say what *kind* of sentence to expect, not its words: the data is live.
If an answer is not what you want, do not edit it in: record that question again. (Names below: Lyon 3-2 Crystal Palace, Europa League, 15 October 2026.)

| # | Say | Expect | Gap line |
|---|---|---|---|
| 1 | "Follow Lyon." | One sentence with the score. The strip appears at the top with the sport, the clock and the date; the eye stays clear. | "I just name a team." |
| 2 | "Who scored?" | The goals in order, with assists. | "Straight facts." |
| 3 | "Who assisted Pino's goal?" | One sentence naming the assist. | "It answers the question I asked." |
| 4 | "Show me the line-ups." | The pitch: home left, away right, shapes, goalkeepers, benches, the ground and date above it. | "A whole screen from one sentence." |
| 5 | "My TV is about forty seconds behind." then "What's the score?" | It confirms; the score holds back anything your picture has not shown. | "It won't spoil a goal your TV hasn't shown." |
| 6 | (live only) say nothing for 12 s | Commentary starts by itself. Say "stop" to interrupt. | "It keeps me posted, and I can interrupt." |

Notes for the take:
- A model answer takes about **2 to 4 seconds** once warm (a plain score is under a second); after 6 seconds the page shows "Still working on it…". Do not cut it.
- If the match is not live, skip question 6 and say "and when a match is in play, it keeps me posted". Never fake a clock.
- If a "Sorry, an error occurred" appears, the model account was throttled: wait 20 seconds and ask again.
- Question 5 also proves the guard: a total such as the stats table is held back for a delayed listener.
- Do not say, or put on a card, anything you have not seen: no number of users, no claim of testing with blind users beyond what the team will state first-hand, no claim of running on real Alexa+, no claim that it is hosted on AWS.

## After recording

1. Trim to under **2:55**. Add captions (auto-generate, then correct names and the model name).
2. Check the frames for keys, emails, account ids, club crests, logos: scrub or crop.
3. Upload as **public** (YouTube or Vimeo), no music, title "Sideline: a friend for the match, in your ear".
4. Put the link in the Devpost form, and in [HACKATHON.md](HACKATHON.md) ("Demo video"). Then replace "to be recorded".
5. Submit before **Friday 23 October 2026, 12:00 pm Pacific** (23:00 in Mauritius). Nothing can change after.

## If a live answer goes wrong on camera

Say so and retake; a faked take is worse than a second one. If the feed is down, use a finished match, or `python3 scripts/ask.py`.
Never speed up or splice an answer so it looks faster than it was: the latency numbers in the docs are measured, and the video should match them.
