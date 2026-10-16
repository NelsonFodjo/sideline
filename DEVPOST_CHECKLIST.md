# What goes in the Devpost form

A working checklist for the *Build, Ship, Shape: Amazon Developer Hackathon* submission. Everything marked **copy** is ready
to paste; everything marked **you** only you can do. The form's exact fields can change, so tick each against the live form
at <https://amazonappdev2026.devpost.com/> before you submit. Deadline: **Friday 23 October 2026, 12:00 pm Pacific
(23:00 in Mauritius)**. Nothing can be changed after it, except to remove infringing or personal material.

## 1. Before you open the form

- [ ] **you** Commit and push (`git add -A`, read `git status`, then commit). `.env` is ignored; check no key is staged.
- [ ] **you** The repository is **public**, and GitHub's About box shows the **MIT** licence (the rules want it detectable).
- [ ] **you** Record the video from [docs/VIDEO_SCRIPT.md](docs/VIDEO_SCRIPT.md), upload it **public** (YouTube or Vimeo), under 3 minutes,
      English, captions on, no music, no third-party logos.
- [ ] **you** Decide whether the two team-reported claims stay (one blind listener tried it; a real microphone session). Keep them only if true.
- [ ] Put the video link in [docs/HACKATHON.md](docs/HACKATHON.md) ("Demo video": replace "to be recorded").
- [ ] `make test` passes on a fresh clone (`git clone <repo> /tmp/x && cd /tmp/x && make test`).

## 2. The form, field by field

| Field | What to put |
|---|---|
| **Project name** | **copy** `Sideline` |
| **Tagline** | **copy** `A friend for the match, in your ear: live sport by voice, built first for people who cannot see the screen.` |
| **Track** | **Alexa+** (a self-hosted MCP server) |
| **Mini challenge** | **AWS Builder**. The Open Source mini challenge is **not** entered (see [docs/HACKATHON.md](docs/HACKATHON.md)); do not tick it unless you add a real contribution first |
| **Elevator pitch** | **copy** the "Elevator Pitch" in [docs/HACKATHON.md](docs/HACKATHON.md) |
| **About the project** (the long text) | **copy** sections 1 to 6 of "Devpost Pitch & Submission Copy" in [docs/HACKATHON.md](docs/HACKATHON.md): Inspiration, What it does, How we built it, Challenges, Accomplishments, What's next. Add what you learned if the form has that field (the friction log and feature requests are the honest answer) |
| **Built with** (tags) | `Python`, `Model Context Protocol (MCP)`, `Amazon Bedrock`, `Amazon Nova Pro`, `Amazon Polly`, `Amazon DynamoDB`, `Mistral Voxtral (Bedrock)`, `Amazon Nova 2 Sonic`, `ESPN public data`, `JavaScript (Web Audio, simulator page)` |
| **Try it out / links** | The public GitHub URL. No hosted demo is needed (the FAQ accepts a locally runnable public repo plus the video; re-check the FAQ wording). The README's "Run it" section is the judge's path: `git clone`, `make run`, open `http://127.0.0.1:8765/`. The live data needs no key |
| **Demo video** | **you** the public video URL |
| **Images / screenshots** | **you** 3 to 4: the simulator mid-answer, the Dev log panel (Alt+D), a terminal with `make test` passing, the friction log's table. Crop out keys, emails and any logos |
| **Testing instructions for judges** | **copy** `No account or key is needed for the data. Python 3.8+. git clone <repo> && cd sideline && make run, then open http://127.0.0.1:8765/ (Chrome or Edge, allow the microphone once). Without AWS credentials the server answers every tool in templated wording through any MCP client; the simulator's voice agent needs Bedrock. make test runs the 61 offline suites with no network or credentials. Hosting is not required.` |
| **AWS services used** (AWS Builder: must be described in the answer, not only the repo) | **copy** the table in [docs/HACKATHON.md](docs/HACKATHON.md) ("AWS services": Bedrock Nova Pro, Voxtral, Nova 2 Sonic, Polly, DynamoDB, each with what it does) and say plainly that AgentCore, Strands and Kiro are **not** used |
| **Product feedback** (every tool, API and SDK used, each with what you used it for, what worked, what needs work, onboarding, and whether you would build with it again) | **copy** all of [docs/PRODUCT_FEEDBACK.md](docs/PRODUCT_FEEDBACK.md). It ends each section with the yes or no |
| **Friction log** (optional; up to +10% from Amazon's review, assessed in Stage 1) | **copy or attach** [docs/FRICTION_LOG.md](docs/FRICTION_LOG.md): 28 entries, each with task, steps, expected, actual, severity, workaround, suggestion. Lead with the summary table |
| **Feature requests** (optional) | **copy** [docs/FEATURE_REQUESTS.md](docs/FEATURE_REQUESTS.md): 9 requests with urgency |
| **If the project existed before 31 August: what changed in the window** | **copy** `Nothing predates the window: the first commit is dated 2026-10-12.` |
| **Third-party material and terms** | **copy** the table in [docs/HACKATHON.md](docs/HACKATHON.md) ("Third-party material and terms"). Be upfront that ESPN's endpoints are public but undocumented and carry no licence or stability promise |
| **Team / representative** | **you** One Devpost representative submits for a team. Add every member to the project |

## 3. Things that lose points if they are wrong

- **Do not** claim the real Alexa+ was used. The README says what is true: a simulated Alexa+ page, because the add-on tooling is partner-only.
- **Do not** claim hosting, OAuth or account linking. They are not built, and the README says so.
- **Do not** paste numbers that are not in the repo. The ones that are: 30 tools, 5 sports, 61 offline suites, routing 77 of 79 on Nova Pro,
  a first question about 6 s cold and 0 to 3 s after, 27 friction entries, 9 feature requests.
- **Keep the video honest.** It must not speed up or splice an answer so it looks faster than it was.
- **Check the video** frame by frame for keys, email addresses, account ids and club crests or broadcast footage.

## 4. The last hour

1. Submit as the one Devpost representative, with time to spare for a form error.
2. Open the public project page in a private window and check: the video plays, every link works, the licence shows, and no text still says "to be recorded".
3. If a link needs fixing, do it now: after the deadline only infringing or personal material can be removed.

Amazon's office hours: Monday 19 October, 9:00 am Pacific (20:00 in Mauritius), if you want to ask the organisers anything first.
