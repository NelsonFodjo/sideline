"""Every relative link in the Markdown and HTML docs points at a file that exists, and every #anchor at a heading.

Offline: links to other sites are not fetched (they change on their own schedule, and CI must not depend on them).
Run: python3 scripts/check_links.py        exit status 1 and a list when something is broken.
"""

import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "logs", "__pycache__", ".claude"}
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)|!\[[^\]]*\]\(([^)\s]+)\)|(?:href|src)=\"([^\"]+)\"")


def slug(heading):
    """GitHub's anchor for a heading: lower case, punctuation dropped, spaces to hyphens."""
    h = unicodedata.normalize("NFKC", heading).strip().lower()
    h = re.sub(r"<[^>]+>", "", h)
    h = re.sub(r"[^\w\- ]", "", h)
    return h.replace(" ", "-")


def anchors(path):
    out = set()
    if not path.endswith(".md"):
        return out
    seen = {}
    in_code = False
    for line in open(path, encoding="utf-8"):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        m = None if in_code else re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        if m:
            s = slug(m.group(1))
            n = seen.get(s, 0)
            seen[s] = n + 1
            out.add(s if n == 0 else "%s-%d" % (s, n))
        for a in re.findall(r"<a\s+(?:name|id)=\"([^\"]+)\"", line):
            out.add(a)
    return out


def docs():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith((".md", ".html")) and f != "index.html":
                yield os.path.join(base, f)


def main():
    broken = []
    for path in sorted(docs()):
        text = open(path, encoding="utf-8").read()
        text = re.sub(r"```.*?```", "", text, flags=re.S)          # code samples are not links
        text = re.sub(r"`[^`\n]*`", "", text)
        for m in LINK.finditer(text):
            target = next(g for g in m.groups() if g)
            if re.match(r"^(?:[a-z]+:|//|#$|\{|\$)", target, re.I):
                continue                                           # another site, mail, data: or a template
            file_part, _, anchor = target.partition("#")
            dest = path if not file_part else os.path.normpath(os.path.join(os.path.dirname(path), file_part))
            rel = os.path.relpath(path, ROOT)
            if not os.path.exists(dest):
                broken.append("%s: %s (no such file)" % (rel, target))
            elif anchor and os.path.isfile(dest) and dest.endswith(".md") and anchor not in anchors(dest):
                broken.append("%s: %s (no such heading)" % (rel, target))
    if broken:
        print("broken links:\n  " + "\n  ".join(broken))
        sys.exit(1)
    print("links: all good")


if __name__ == "__main__":
    main()
