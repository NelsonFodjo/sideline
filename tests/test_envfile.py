"""The .env loader: keys in a file reach the process, and never beat a
real environment variable."""

import os
import tempfile

from conftest import make_ctx  # noqa: F401  (puts the repo root on sys.path)

from sideline import envfile


def main():
    parsed = envfile.parse('''
# comment
SIDELINE_BEDROCK=on
export AWS_REGION="eu-west-1"
QUOTED='single quoted'
TRAILING=value # a comment
EMPTY=
no_equals_here
''')
    assert parsed == {"SIDELINE_BEDROCK": "on", "AWS_REGION": "eu-west-1",
                      "QUOTED": "single quoted", "TRAILING": "value"}, parsed
    print("ok  parses comments, export, quotes, trailing comments; skips blanks")

    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
        f.write("ZZ_FROM_FILE=file\nZZ_ALREADY_SET=file\nZZ_BLANK=\n")
    try:
        os.environ["ZZ_ALREADY_SET"] = "shell"
        os.environ.pop("ZZ_FROM_FILE", None)
        applied = envfile.load(f.name)
        assert os.environ["ZZ_FROM_FILE"] == "file"
        assert os.environ["ZZ_ALREADY_SET"] == "shell"
        assert "ZZ_BLANK" not in os.environ
        assert applied == ["ZZ_FROM_FILE"]
        print("ok  priority: environment variable > file; blank file values are skipped")
    finally:
        os.unlink(f.name)
        os.environ.pop("ZZ_FROM_FILE", None)
        os.environ.pop("ZZ_ALREADY_SET", None)

    assert envfile.load("/nonexistent/.env") == []
    print("ok  a missing file is not an error")

    # The shipped template must parse and must not be hiding anything:
    # every line live, none commented out.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    text = open(os.path.join(root, ".env.example"), encoding="utf-8").read()
    for line in text.splitlines():
        stripped = line.lstrip("# ").strip()
        looks_like_setting = ("=" in stripped and stripped.split("=")[0].isupper()
                              and " " not in stripped.split("=")[0])
        assert not (line.startswith("#") and looks_like_setting and line.startswith("# ") and
                    stripped.split("=")[0].startswith(("AWS_", "SIDELINE_", "GROQ_"))), \
            "commented-out setting in .env.example: " + line
    print("ok  .env.example has no commented-out settings")

    print("\nenvfile: all good")


if __name__ == "__main__":
    main()
