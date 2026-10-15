"""Load a .env file into os.environ, standard library only.

So that "add your keys and start it" is literally `cp .env.example .env`,
edit, run. Called from sideline/__init__.py BEFORE anything else is
imported, because several modules read the environment at import time.

PRECEDENCE, highest first:
  1. a real environment variable (a shell `export`) - ALWAYS wins
  2. this file
  3. the built-in default

So environment variables are the priority; the file is only a
convenience for the ones you have not exported. It is git-ignored.

Rules, kept deliberately small:
  * KEY=value lines; `#` comments (also after a value: `KEY="abc" # note`);
    optional `export `; optional quotes.
  * Empty values are skipped, so a blank `AWS_ACCESS_KEY_ID=` in a copied
    .env.example never masks anything.
"""

import os


def parse(text):
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if value[:1] in ("\"", "'") and value.find(value[0], 1) != -1:
            # Quoted: the value is what is inside the quotes; a `# comment` may follow them.
            end = value.find(value[0], 1)
            rest = value[end + 1:].strip()
            if not rest or rest.startswith("#"):
                value = value[1:end]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key and value:
            out[key] = value
    return out


def load(path=None):
    """Returns the names it set. Never raises on a missing file."""
    if path is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, ".env")
    try:
        with open(path, encoding="utf-8") as f:
            values = parse(f.read())
    except OSError:
        return []
    applied = []
    for k, v in values.items():
        if k not in os.environ:
            os.environ[k] = v
            applied.append(k)
    return applied
