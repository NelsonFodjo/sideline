"""The simulator's developer log (toggle bottom-left, Alt+D): run its real code in Node against a stand-in for the page.

It must: start empty on every load (a refresh clears it), keep entries in local storage, show the model, each model call,
each MCP tool with its arguments and time, and the speech timings, and never treat what the feed or the model said as
markup (everything is set with textContent)."""

import json
import os
import re
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, "..", "simulator", "index.html")

HARNESS = r"""
const store = {};
global.localStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } };
store["sideline.devlog"] = JSON.stringify([{stale: true}]);           // what a previous page left behind
class El { constructor(t){ this.tag=t; this.children=[]; this._text=""; this.className=""; this.hidden=false; this.attrs={}; this.onclick=null; }
  appendChild(c){ this.children.push(c); return c; } setAttribute(k,v){ this.attrs[k]=v; }
  set textContent(v){ this._text=String(v); this.children=[]; } get textContent(){ return this._text + this.children.map(c=>c.textContent).join(""); }
  get innerHTML(){ throw new Error("innerHTML must never be used"); } set innerHTML(v){ throw new Error("innerHTML must never be used"); } }
const els = {}; ["devbtn","devpanel","devclear","devcopy","devcount","devlist"].forEach(id => { els[id] = new El("div"); });
els.devpanel.hidden = true;
global.document = { getElementById: id => els[id], createElement: t => new El(t), addEventListener(){} };
Object.defineProperty(global, "navigator", { value: { clipboard: { writeText(t){ global.copied = t; } } }, configurable: true });   // Node has its own
global.performance = { now: () => 1000 };
global.$ = () => ({});
%s
// ---- 1. a fresh load starts empty
if (store["sideline.devlog"] !== undefined) throw new Error("the previous page's log must be wiped on load");
// ---- 2. an answer from the model, with tools, tokens, speech in and out
devInput = "what is the score";
devStt = {provider: "voxtral", ms: 640};
const result = {text: "Arsenal lead one-nil.", generated_by: "bedrock-fast", model: "us.anthropic.claude-haiku-4-5",
  debug: {ms: 1180, model: "us.anthropic.claude-haiku-4-5", model_calls: [{ms: 412, input_tokens: 5120, output_tokens: 38, stop: "tool_use"}],
          tools: [{name: "get_match_state", args: {team: "Arsenal"}, ms: 87, ok: true, declined: false}]}};
devRecord(devFromAnswer(result, 0));
devNoteTts(390, 21, "polly");
devToggle(true);
const shown = els.devlist.textContent;
for (const want of ["what is the score", "voxtral", "640 ms", "bedrock-fast", "us.anthropic.claude-haiku-4-5", "1 call", "412 ms", "5120 in / 38 out",
                    "get_match_state", '{"team":"Arsenal"}', "87 ms", "ok", "Arsenal lead one-nil.", "polly", "390 ms"])
  if (!shown.includes(want)) throw new Error("the log does not show: " + want + "\n" + shown);
// ---- 3. persisted in local storage, and the copy button gives JSON
const saved = JSON.parse(store["sideline.devlog"]);
if (saved.length !== 1 || saved[0].tools[0].name !== "get_match_state" || saved[0].tts[0].provider !== "polly") throw new Error("not persisted: " + store["sideline.devlog"]);
els.devcopy.onclick(); if (JSON.parse(global.copied).length !== 1) throw new Error("copy must give the entries as JSON");
// ---- 4. hostile text is text
devInput = "<img src=x onerror=alert(1)>";
devRecord(devFromAnswer({text: "<script>alert(2)</script>", generated_by: "nova", debug: {model_calls: [], tools: []}}, 0));
if (!els.devlist.textContent.includes("<script>alert(2)</script>")) throw new Error("hostile text must be shown as text");
// ---- 5. an error is an entry; failed model calls say so; Clear empties it
devRecord({kind: "error", note: "agent call failed", error: "agent unavailable"});
devRecord(devFromAnswer({text: "", generated_by: "nova", debug: {model_calls: [{ms: 9, error: "ThrottlingException"}], tools: []}}, 0));
if (!els.devlist.textContent.includes("failed: ThrottlingException") || !els.devlist.textContent.includes("agent unavailable")) throw new Error("errors must show");
els.devclear.onclick(); if (devEntries.length !== 0 || JSON.parse(store["sideline.devlog"]).length !== 0) throw new Error("Clear must empty the log and its storage");
// ---- 6. closed means closed
devToggle(false); if (!els.devpanel.hidden || els.devbtn.attrs["aria-expanded"] !== "false") throw new Error("the toggle must close the panel");
console.log("ok");
"""


def main():
    node = shutil.which("node")
    if not node:
        print("skip  node is not installed: the developer log's page code was not run")
        return
    with open(HTML, encoding="utf-8") as fh:
        page = fh.read()
    start = page.index("/* ============================================================ developer log")
    end = page.index("try{ devToggle(localStorage.getItem(DEV_ON_KEY)===\"1\"); }catch(e){ devRender(); }") + len(
        "try{ devToggle(localStorage.getItem(DEV_ON_KEY)===\"1\"); }catch(e){ devRender(); }")
    code = page[start:end]
    assert "innerHTML" not in code, "the developer log must not use innerHTML"
    out = subprocess.run([node, "-e", HARNESS % code], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0 and out.stdout.strip() == "ok", out.stdout + out.stderr
    print("ok  the developer log: wiped on load, saved to local storage, shows model, calls, tools with arguments, speech timings;")
    print("    hostile text stays text; errors show; Clear and the toggle work")
    assert "<150ms" not in page and "<150 ms" not in page, "the page must not claim a response time it does not have"
    print("ok  the page no longer claims '<150ms'")


if __name__ == "__main__":
    main()
    print("\ndev log: all good")
