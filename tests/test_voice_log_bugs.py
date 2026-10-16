"""Bugs found in a real session's log (16 October 2026), each pinned so it cannot come back.

- Voxtral answered instead of transcribing ("I'm sorry, I can't understand that...") and that reached the agent as a question.
- One phrase repeated on room noise ("Bonjour. Bonjour. Bonjour.", "Yeah. Yeah. Yeah.") was asked as a question.
- A "yeah" in the middle of room talk was taken as yes to an old offer: "Yeah, he's not here..." became Sydney FC.
- The first question of a session failed on one Bedrock read timeout.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from simulator import voice, agent           # noqa: E402
from sideline import resolve                 # noqa: E402


def main():
    for said in ["I'm sorry, I can't understand that. Could you please repeat or clarify what you said?",
                 "I'm sorry, but I can't assist with that.",
                 "I'm sorry, but I can't process or understand audio content. However, if you have a text or transcript"]:
        assert voice.assistant_reply(said), said
    for real in ["Sorry, can you repeat that?", "Could you repeat the score?", "I can't hear the TV, what's the score?",
                 "Sorry, who scored?", "I'm sorry I missed the goal, who scored?"]:
        assert not voice.assistant_reply(real), real
    print("ok  the recogniser's own apology is dropped; a listener asking to repeat, or saying sorry, is kept")

    for noise in ["Bonjour. Bonjour. Bonjour.", "Yeah. Yeah. Yeah.", "Oh. Oh.", "I don't know. I don't know. I don't know."]:
        assert voice.repeated_phrase(noise), noise
    for real in ["Go on, go on.", "Who scored? Who scored first?", "Yeah.", "Arsenal. Arsenal.", "When was it?", "No, no, no."]:
        assert not voice.repeated_phrase(real), real
    print("ok  one phrase said over and over on room noise is dropped; a real reply that repeats a name is kept")

    class Offer:
        def __init__(self, label):
            self.label = self.say = self.agent_say = label
            self.aliases = [resolve.words(label)]
    lid = "log-bugs"
    for text, expect in [("Yeah, he's not here and he has a meeting at 2. I have a meeting with him at 2.", False),
                         ("Do you want to meet him? Yes, sir. That would be great.", False),
                         ("yeah", True), ("Yes please", True), ("yeah, the next one", True)]:
        resolve.BOOK.get = lambda _l, _n=None: [Offer("Sydney FC")]
        resolve.BOOK.clear = lambda _l: None
        got = resolve.snap(lid, text)
        assert (got["why"] == "affirmation") == expect, (text, got)
    print("ok  'yes' takes the offer only when it starts a short reply, never from the middle of room talk")

    calls = []

    def converse(**_):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError('Read timeout on endpoint URL: "https://bedrock-runtime.us-east-1.amazonaws.com/..."')
        return {"output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}}, "usage": {}}
    keep = agent._converse
    agent._converse = converse
    try:
        assert agent._ask("s", [{"role": "user", "content": [{"text": "q"}]}])["output"]["message"]["content"][0]["text"] == "ok"
        assert len(calls) == 2
        calls.clear()

        def denied(**_):
            calls.append(1)
            raise RuntimeError("AccessDeniedException: not authorized")
        agent._converse = denied
        try:
            agent._ask("s", [{"role": "user", "content": [{"text": "q"}]}])
            raise AssertionError("an access error must fail")
        except agent.AgentUnavailable:
            pass
        assert len(calls) == 1, "only a timeout or a throttle is tried again"
    finally:
        agent._converse = keep
    print("ok  one read timeout or throttle is tried once more; any other failure is not")

    page = open(os.path.join(ROOT, "simulator", "index.html"), encoding="utf-8").read()
    assert "if(spec.text===prevSpec)" in page, "the same finished sentence twice is the question, in a noisy room"
    assert "FRAGMENT_RE.test(t)" in page and "!isAssistantEcho(t)) liveSaid" in page
    print("ok  page: a noisy room no longer re-sends the clip; a lone 'I'm' is not a question; her voice is never captioned as yours")
    print("\nvoice log bugs: all good")


if __name__ == "__main__":
    main()
