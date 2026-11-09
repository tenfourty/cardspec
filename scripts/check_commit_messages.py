"""Commit messages in this repository carry no tool attribution: no co-author, sign-off or
session lines. Used by the commit-msg hook (scripts/hooks/commit-msg) and by CI over a range.

    python3 scripts/check_commit_messages.py <rev-range>     # e.g. origin/main..HEAD

With COMMIT_IDENTITY set (for example "Name <name@example.com>", from the forge's repository
variables), every commit in the range must also be authored and committed by that identity.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

FORBIDDEN = re.compile(
    r"^\s*(co-authored-by|signed-off-by|claude-session)\s*:|generated with \[?claude", re.I | re.M
)


def problems(message: str) -> list[str]:
    return [m.group(0).strip() for m in FORBIDDEN.finditer(message)]


def identity_problems(identity: str, rev_range: str, cwd=None) -> list[str]:
    """Commits in `rev_range` whose author or committer is not `identity`; none if it is empty."""
    if not identity.strip():
        return []
    out = subprocess.run(
        ["git", "log", "--format=%H %an <%ae>|%cn <%ce>", rev_range],
        capture_output=True,
        text=True,
        check=True,
        cwd=cwd,
    ).stdout
    found = []
    for line in filter(None, out.splitlines()):
        sha, _, people = line.partition(" ")
        author, _, committer = people.partition("|")
        for role, who in (("author", author), ("committer", committer)):
            if who != identity.strip():
                found.append(f"{sha[:12]}: {role} is {who}")
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    out = subprocess.run(
        ["git", "log", "--format=%H%x00%B%x01", argv[1]], capture_output=True, text=True, check=True
    ).stdout
    bad = 0
    for entry in filter(str.strip, out.split("\x01")):
        sha, _, message = entry.strip().partition("\x00")
        for found in problems(message):
            print(f"{sha[:12]}: commit message carries '{found}'", file=sys.stderr)
            bad += 1
    for problem in identity_problems(os.environ.get("COMMIT_IDENTITY", ""), argv[1]):
        print(f"{problem}, not the repository's commit identity", file=sys.stderr)
        bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
