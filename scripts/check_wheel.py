"""Check a built wheel: no runtime dependencies, and LICENSE and NOTICE are inside.

python3 scripts/check_wheel.py dist/*.whl
"""

from __future__ import annotations

import sys
import zipfile


def main(path: str) -> int:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        meta = next(n for n in names if n.endswith(".dist-info/METADATA"))
        requires = [
            ln for ln in z.read(meta).decode().splitlines() if ln.startswith("Requires-Dist")
        ]
    problems = []
    if requires:
        problems.append(f"runtime dependencies found: {requires}")
    for needed in ("LICENSE", "NOTICE"):
        if not any(n.endswith("/licenses/" + needed) or n.endswith("/" + needed) for n in names):
            problems.append(f"{needed} is not in the wheel")
    for p in problems:
        print(p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
