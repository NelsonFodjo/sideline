"""The line-ups view: home on the left, away on the right, each side in the shape it lined up in, with the bench.

Runs the page's real layout code in Node on a real line-up (Lyon 3-2 Crystal Palace, Europa League), and checks the wiring.
"""

import json
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = open(os.path.join(ROOT, "simulator", "index.html"), encoding="utf-8").read()
DATA = json.load(open(os.path.join(ROOT, "tests", "fixtures", "lineups-lyon-palace.json")))


def _extract():
    a = PAGE.index("/* ============================================================== line-ups")
    b = PAGE.index("function showLineups(sc){", a)
    return PAGE[a:b]


def main():
    node = shutil.which("node")
    if not node:
        print("skip  node is not installed: the line-up layout harness did not run")
        return
    code = _extract() + """
var D = %s, out = {};
Object.keys(D.lineups).forEach(function(t){
  var x = D.lineups[t];
  var cols = luColumns(x.xi, x.positions, x.formation);
  out[t] = cols.map(function(c){ return c.map(function(p){ return p.name; }); });
});
out.broken = luColumns(["A","B","C"], {A:"goalkeeper",B:"left back",C:"striker"}, "9-9").map(function(c){ return c.length; });
out.abbr = [luAbbr("goalkeeper"), luAbbr("center left defender"), luAbbr("left back"), luAbbr("defensive midfielder"), luAbbr("center right forward")];
console.log(JSON.stringify(out));
""" % json.dumps(DATA)
    proc = subprocess.run([node, "-e", code], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])

    lyon, palace = out["Lyon"], out["Crystal Palace"]
    assert [len(c) for c in lyon] == [1, 4, 1, 2, 1, 2], [len(c) for c in lyon]
    assert lyon[0] == ["Dominik Greif"] and lyon[1][0] == "Abner" and lyon[1][-1] == "Zachary Athekame", lyon[1]
    assert lyon[2] == ["Tyler Morton"] and lyon[4] == ["Khalis Merah"]
    print("ok  Lyon's 4-1-2-1-2 comes out as a goalkeeper, four across the back (left back to right back), one, two, one, two")
    assert [len(c) for c in palace] == [1, 3, 4, 2, 1], [len(c) for c in palace]
    assert palace[4] == ["Jørgen Strand Larsen"] and sorted(palace[3]) == ["Ismaïla Sarr", "Yéremy Pino"], palace
    assert palace[2][0] == "Tyrick Mitchell" and palace[2][-1] == "Óscar Mingueza"
    print("ok  Palace's 3-4-2-1: a lone striker at the front, two behind him, the four across midfield from left to right")
    assert out["broken"] == [1, 1, 1], out["broken"]
    print("ok  a shape that does not add up falls back to one column per step up the pitch")
    assert out["abbr"] == ["GK", "CB", "LB", "DM", "FW"], out["abbr"]
    print("ok  positions get their short names")

    assert 'id="lineup"' in PAGE and "showLineups(lu)" in PAGE and "else if(!luMentions(result&&result.text)) hideLineups()" in PAGE
    assert PAGE.count("hideLineups()") >= 4, "it goes when you speak, when the words clear, on the x, and on the next answer"
    assert "luTeam(pitch,away,sc.lineups[away],true)" in PAGE, "the away side is drawn from the right"
    a = PAGE.index("function luNorm("); b = PAGE.index("function luOpen(")
    keys = subprocess.run([node, "-e", PAGE[a:b] + """
console.log(JSON.stringify([luKey("Jørgen Strand Larsen"), luKey("Óscar Mingueza"), luNorm("Pino's,"), luNorm("Mingueza."), luKey("Abner")]));
"""], capture_output=True, text=True, timeout=30)
    assert json.loads(keys.stdout) == ["larsen", "mingueza", "pino", "mingueza", "abner"], keys.stdout + keys.stderr
    assert "m.dataset.sur=luKey(pl.name)" in PAGE and "luGlow(spans[cur].textContent)" in PAGE
    print("ok  a player she names lights up as the word is spoken; a question about a player on the line-ups keeps them open")
    src = open(os.path.join(ROOT, "sideline", "tools", "get_lineups.py")).read()
    assert '"teams": {"home"' in src, "the tool says which side is home"
    print("ok  wired: shown for get_lineups, hidden on the next question or when the words clear, away side mirrored")
    print("\nlineups view: all good")


if __name__ == "__main__":
    main()
