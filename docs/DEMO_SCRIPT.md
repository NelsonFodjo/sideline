# The demo video

Rules (Devpost, read 2026-10-12): under three minutes, public on YouTube or
Vimeo, English, showing the project functioning, **no third-party
trademarks or copyrighted material** without permission. Judges "are not
required to test the Project and may choose to judge based solely on the
text description, images, and video", so the video carries real weight.

## What the video can and cannot show

- **Cannot:** a real Alexa+ device, the Alexa developer console, or the
  `alexa-ai` tooling. The FAQ says they are partner-only.
- **Can, and the FAQ says it satisfies the track:** a web page acting as a
  real MCP client (initialize, tools/list, tools/call over Streamable
  HTTP). That is the simulator, served at http://127.0.0.1:8765/.
- **Optional bonus per the FAQ:** an existing AI assistant app calling the
  same server. Untested here; try it before promising it.

## Shot list (a plan, not a recording; times are targets)

| Time | Shot | Why |
|---|---|---|
| 0:00–0:25 | Voiceover on a plain background: what is lost when you cannot see a football broadcast (line-ups shown once, score on screen, referee named once). Then who it is for. | The problem, in the rules' terms of "a credible, specific case". No logos. |
| 0:25–1:05 | Simulator, real match. Ask "what did I miss". Show the answer, the `told` marker and the gap band closing. Ask again: nothing new. | The per-listener `last_told_at` state: the rules name state across sessions as a creative Alexa+ idea. |
| 1:05–1:40 | "Who's refereeing?" (Michael Oliver, 5 yellows and 1 red, from the data), "tell me about that goal", "who's playing". | The facts a broadcast shows once. Say it is a recorded match. |
| 1:40–2:10 | The machine strip and the raw MCP calls: which tool ran, how long, and `generated_by`. | Shows the MCP is real and the Bedrock path is visible. Only show `bedrock` if it really ran. |
| 2:10–2:35 | Restart the server; ask again; it still knows what was already said. **Only if DynamoDB state is verified working**, otherwise cut this. | State across sessions, demonstrated. |
| 2:35–2:55 | One sentence each: who it helps and how it could reach more people. | Potential Impact. |

## Hard rules

- **No club badges, league logos, broadcast clips, stadium branding.** Club
  names in text and in the data are fine. Say "data from StatsBomb Open Data".
  Their terms ask for their logo too: not included; see DATA_PROVIDERS.md.
- **No crowd or commentary audio** you do not own. Use silence, or audio you
  recorded or generated yourself.
- **Say what the data is:** "a recorded match, replayed". Never imply live.
- **Do not claim what has not been measured.** Latency figures on screen
  must come from `docs/EVIDENCE.md` or from your own `make aws-check`.
- **Do not say it works with Alexa+ devices.** It has not been connected to one.

## A real user, if you can get one

The rules score Potential Impact on whether the project "makes a credible,
specific case for solving customer needs". Nobody has tested Sideline with
a blind or low-vision person. A short, real, unscripted session, with
consent, is the one thing that turns an argument into evidence. If it does
not happen, say plainly in the text description that it has not.

## Before filming

```bash
make test                       # green
make run                        # terminal 1
make sim                        # opens the simulator
SIDELINE_REPLAY_SPEED=1 SIDELINE_REPLAY_START=36 make run   # start near the first goal
```

If the live feed is unavailable, the replay is the identical code path.
