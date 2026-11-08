"""The problems a card can have, reported as data a person or a model can act on."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Issue:
    """One problem found in a card.

    `path` is a JSON pointer (RFC 6901) into the document that was checked, for example
    `/elements/steps/props/rows/1`. `code` is stable: code may match on it. `message` is plain
    English and says how to fix the problem. `limit` and `actual` are set when a number was
    too big or too small.
    """

    path: str
    code: str
    message: str
    limit: int | None = None
    actual: int | None = None

    def to_dict(self) -> dict[str, str | int]:
        out: dict[str, str | int] = {"path": self.path, "code": self.code, "message": self.message}
        if self.limit is not None:
            out["limit"] = self.limit
        if self.actual is not None:
            out["actual"] = self.actual
        return out


class CardError(Exception):
    """Raised when a card cannot be used; `issues` says why."""

    def __init__(self, issues: Iterable[Issue]) -> None:
        self.issues: list[Issue] = list(issues)
        shown = "; ".join(f"{i.code} at {i.path or '/'}: {i.message}" for i in self.issues[:5])
        more = len(self.issues) - 5
        suffix = f" (and {more} more)" if more > 0 else ""
        super().__init__(f"{len(self.issues)} issue(s): {shown}{suffix}")


def pointer(*parts: object) -> str:
    """Build a JSON pointer from parts, escaping `~` and `/` in each."""
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)
