# Prompt for the explainer animation

Use this to have Claude build the 30 to 35 second "what happens behind the answer" animation for the video. Paste everything
under **"The prompt"** into Claude (claude.ai, with artifacts on, or Claude Code), and attach the screenshots listed below if
you want the end frames to match the real page. Claude should return **one self-contained HTML file** (inline CSS, SVG and JS,
no external files, no network) that plays by itself in a browser at 1920 x 1080 and that you screen-record.

Everything in the prompt is taken from this repository. Nothing is invented: if you change the product, change the facts here
first. A judge may read this file, so it is written to be checked.

## Screenshots to attach (all in `docs/video/screenshots/`)

| File | What it shows | Use it for |
|---|---|---|
| `02-following-a-match.png` | Lyon 3-2 Crystal Palace, a bare score strip over the eye | the "answer arrives on screen" beat |
| `03-timeline-open.png` | the timeline open, goals, the ground and the date | the "structured data" beat |
| `10-lineups.png` | the line-ups pitch, home left, away right, benches | the "one question, a whole screen" beat |
| `11-basketball-following.png` | Knicks 122-120 Raptors, Final, quarters on the timeline | the "same pipe, new sport" beat |
| `13-american-football-following.png` | Broncos 17-14 Seahawks, Final | the "same pipe, new sport" beat |
| `09-dev-log.png` | the Dev log: tool, arguments, feed requests, timings | the "everything is visible" beat |

## The prompt

> Build a single self-contained HTML file that plays a **32 second explainer animation**, 1920 x 1080, 60 fps, dark theme,
> that shows judges how a voice question becomes an answer through an MCP server. No audio, no external assets, no network
> calls, no logos or crests of any company (write service names as plain text). The animation starts automatically, runs once
> and holds on its last frame. Add a tiny scrubber (hidden unless the mouse moves) so I can seek while recording. Respect
> `prefers-reduced-motion` by holding each scene still for its duration instead of animating.
>
> **Style.** Background `#04070C`. Accent cyan `#19C6F4` for the listener's side, amber `#FFB454` for the data side. Text in
> white `#EAF4FB`, secondary `#8AA4C8`. Font: system sans for words, a monospace for protocol text. Calm, precise motion: ease-out,
> nothing bounces, nothing flashes. One idea per scene, each scene has a short caption at the bottom in plain words (max 12
> words). Big, legible type: this is watched on a phone.
>
> **The product (for context).** Sideline is an MCP server that lets a person ask about a live match by voice and get a
> short spoken answer, without opening an app, searching or typing. It remembers what each listener has already been told,
> and it never tells them a goal their delayed TV has not shown yet. The "client" is Alexa+ (in our demo, a web page that
> simulates it). The server is ours.
>
> **Scenes** (seconds are from the start):
>
> 1. **0 to 4: Someone asks.** A sound wave in cyan, and the words typing in: *"What did I miss?"* Caption: "A listener asks. No app, no search."
> 2. **4 to 9: The host chooses a tool by reading.** On the left, the host (label **Alexa+**, a rounded box). On the right a fan of
>    30 small cards, each a tool name in monospace; show about 12 readable names, e.g. `follow_match`, `get_match_state`,
>    `what_did_i_miss`, `get_lineups`, `get_match_stats`, `get_player_profile`, `get_standings`, `get_fixtures`, `get_schedule`,
>    `get_event_detail`, `get_match_report`, `set_preferences`, and let the rest be unlabelled dots. A line of description text
>    from the tool, "What happened since the listener last heard anything. Say: 'what did I miss'", scans across, and
>    `what_did_i_miss` lights up. Caption: "The host reads the tool descriptions and picks one."
> 3. **9 to 14: The call.** A packet travels from the host to the server box, labelled in monospace with real protocol text:
>    `POST /mcp  {"jsonrpc":"2.0","method":"tools/call","params":{"name":"what_did_i_miss","arguments":{}}}`.
>    Above the arrow, small grey labels `MCP 2025-11-25` and `Streamable HTTP`. Caption: "A standard MCP call. Any MCP client can make it."
> 4. **14 to 22: Inside the server** (the main scene, linger). Draw the **Sideline MCP server** as a box with three lanes the
>    packet passes through, left to right:
>    - **Listener memory:** a small table row `last_told_at: minute 34` and `told_event_ids: 6`, with a pill "stored in Amazon DynamoDB".
>      Caption: "It knows what you were already told."
>    - **Live feed:** a clock icon and the text `live data is cached 3 to 5 seconds`, a pill "ESPN public feeds",
>      two requests arrow out and back. Caption: "Live means live."
>    - **Spoiler guard:** a timeline bar with a notch labelled "your TV" behind a notch labelled "live", and a goal marker that stays
>      greyed out until the "your TV" notch reaches it. Caption: "It will not spoil a goal your TV has not shown."
>    The packet exits carrying a result.
> 5. **22 to 27: The answer comes back in two forms.** The result splits into **`content`** (the words to speak, in a speech
>    bubble: "Since minute 34: a penalty, saved. Nothing else.") and **`structuredContent`** (a small JSON snippet
>    `{"score":{"home":3,"away":2},"minute":90,"sport":"football"}`). Then the speech bubble becomes a sound wave back to the
>    listener, and the JSON becomes the real screen: **crossfade to `02-following-a-match.png`**, then **`10-lineups.png`**.
>    Caption: "Words for the ear. Data for any screen."
> 6. **27 to 31: Same pipe, any sport.** Quickly swap the screen between `11-basketball-following.png` and
>    `13-american-football-following.png`, with the tool box unchanged underneath and only the clock word changing
>    (`Q3`, `Final`). Caption: "Football, basketball, American football, hockey, baseball."
> 7. **31 to 32: Hold.** Centre text, two lines: **"One MCP server. Every game. No searching."** and below, small:
>    "Built on Amazon Bedrock, Amazon Polly and Amazon DynamoDB."
>
> **A permanent thin strip along the bottom** shows the three AWS services Sideline uses, each as a plain text pill that lights
> up in the scenes where it works, with one line under it:
> - **Amazon Bedrock**: Amazon Nova Pro picks the tools in our simulator; Mistral Voxtral and Amazon Nova Sonic turn speech into text.
> - **Amazon Polly**: the generative voice that speaks, with word timings so the screen can follow along.
> - **Amazon DynamoDB**: what each listener has heard, and the event log.
>
> Do not show any number that is not in this prompt. Do not claim it runs on real Alexa+ (it does not yet). Keep every claim
> to what is written here.
>
> After the HTML, print a short list of the scene start times so I can match narration to it.

## Narration to read over it (about 70 words, 28 seconds: the video uses 28 s of the animation)

> "You ask. The host, Alexa+, reads the tool descriptions and picks one. It calls our server with a standard MCP request.
> Inside, the server checks what you've already been told, reads the live feed, and holds back anything your TV hasn't shown yet.
> The answer goes back two ways: words for your ear, data for any screen. Same pipe for every sport.
> Built on Amazon Bedrock, Polly and DynamoDB."

## The facts behind each beat (so you can defend them)

| Claim in the animation | Where it is true |
|---|---|
| 30 tools, five sports | `python3 -c "from sideline.tools import REGISTRY; print(len(REGISTRY))"` gives 30; [TOOLS.md](../TOOLS.md), [SPORTS.md](../SPORTS.md) |
| MCP spec 2025-11-25, Streamable HTTP, `initialize`, `tools/list`, `tools/call` | [MCP.md](../MCP.md); the official Python SDK client check, `scripts/check_with_sdk.py` |
| `content` and `structuredContent` in every result | [MCP.md](../MCP.md); the page draws its screens from `structuredContent` |
| Per-listener memory (`last_told_at`, told event ids), kept in DynamoDB | [ARCHITECTURE.md](../ARCHITECTURE.md), `sideline/state/` |
| Live data cached only seconds | `sideline/providers/espn.py` (the cache times: scoreboard and a live match summary 5 s, a parsed live match 3 s, schedule 30 s, standings 60 s, news 120 s, a finished match kept for hours) and `tests/test_cache.py` |
| The spoiler guard | README, "What makes it a server and not a lookup"; `tests/test_score_truth.py` |
| Amazon Nova Pro chooses tools (in the simulator) | [BEDROCK.md](../BEDROCK.md): routing 77 of 79 phrasings on Nova Pro. In the demo the host is offered a shortlist of the 30 (four core tools plus up to four by keyword), and some plain questions take a fast path with no model; the scene shows the general MCP pattern, which any host can follow with the full catalog |
| Voxtral and Nova Sonic for speech in, Polly for speech out | [SPEECH.md](../SPEECH.md) |

## If Claude's first attempt is too busy

Say: "Keep scenes 4 and 5 and cut scene 6 to a single swap. Make every caption shorter. Slow scene 4 by two seconds and
speed scene 1 up by two." The server scene is the one judges need to understand.
