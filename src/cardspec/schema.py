"""The schema kit: the typed pieces a catalogue is built from.

Every string a catalogue accepts must name a *role* (title, text, label, cell and so on).
There is no plain string kind, so a catalogue cannot define a string that a later walker or
safety check would miss. A `max` is either a whole number or the name of a number in `Limits`
(for example `"title"`), which is looked up when the card is checked.
"""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .issue import Issue, pointer
from .limits import Limits
from .links import LinkPolicy

#: Roles a text string can have. Web addresses have their own kind (`Url`).
ROLES: tuple[str, ...] = (
    "title",
    "subtitle",
    "text",
    "label",
    "value",
    "header",
    "cell",
    "caption",
    "category",
    "series",
    "segment",
    "alt",
    "button",
)

# Whole numbers beyond this are refused: they are not display values anyone means.
_BIG = 10**15

# Invisible characters outside the Unicode "format" and "control" classes.
_INVISIBLE = frozenset("ᅟᅠㅤﾠ")
_BAD_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp", "Co", "Cs"})


class Full(Exception):
    """Raised inside a check when enough issues have been collected."""


class Ctx:
    """What a check needs while it runs, and where it puts what it finds."""

    def __init__(
        self,
        limits: Limits,
        links: LinkPolicy,
        mode: str = "final",
        max_issues: int = 50,
    ) -> None:
        self.limits = limits
        self.links = links
        self.mode = mode
        self.max_issues = max_issues
        self.issues: list[Issue] = []
        self.chars = 0

    def issue(
        self,
        path: str,
        code: str,
        message: str,
        limit: int | None = None,
        actual: int | None = None,
    ) -> None:
        self.issues.append(Issue(path, code, message, limit, actual))
        if len(self.issues) >= self.max_issues:
            raise Full

    def resolve(self, value: int | str | None) -> int | None:
        if value is None or isinstance(value, int):
            return value
        return int(getattr(self.limits, value))


def _kind_of(value: object) -> str:
    if value is None:
        return "nothing (null)"
    if isinstance(value, bool):
        return "true or false"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "an object"
    return type(value).__name__


def forbidden_char(text: str, multiline: bool = False) -> str | None:
    """The first character in `text` that a card may not hold, as `U+XXXX`, else None."""
    for c in text:
        if c == "\n" and multiline:
            continue
        if c in _INVISIBLE or unicodedata.category(c) in _BAD_CATEGORIES:
            return f"U+{ord(c):04X}"
    return None


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


class Kind:
    """A rule for one value. Subclasses implement `check` and `describe`."""

    def check(self, value: Any, path: str, ctx: Ctx) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def describe(self, limits: Limits) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def limit_names(self) -> list[str]:
        """Names of the `Limits` numbers this kind refers to."""
        return []


@dataclass(frozen=True)
class Opt:
    """Marks an object field or a prop as optional."""

    kind: Kind


def _unwrap(spec: Kind | Opt) -> tuple[Kind, bool]:
    return (spec.kind, False) if isinstance(spec, Opt) else (spec, True)


def _names(*values: object) -> list[str]:
    return [v for v in values if isinstance(v, str)]


@dataclass(frozen=True)
class Str(Kind):
    """Text with a role. `max` is a character count or a `Limits` name."""

    role: str
    max: int | str | None = None
    multiline: bool = False
    allow_empty: bool = False
    number_ok: bool = False

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"role must be one of {', '.join(ROLES)}; got {self.role!r}")

    def limit_names(self) -> list[str]:
        return _names(self.max)

    def check(self, value: Any, path: str, ctx: Ctx) -> None:
        if self.number_ok and isinstance(value, (int, float)) and not isinstance(value, bool):
            if _bad_number(value):
                ctx.issue(path, "bad_number", "numbers must be finite and below a quadrillion")
                return
            shown = str(value)
        elif isinstance(value, str):
            shown = value
        else:
            want = "text or a number" if self.number_ok else "text"
            ctx.issue(path, "wrong_type", f"expected {want}, got {_kind_of(value)}")
            return
        bad = forbidden_char(shown, self.multiline)
        if bad:
            ctx.issue(
                path,
                "forbidden_char",
                f"contains the character {bad}, which is a control, invisible or direction "
                "character; remove it",
            )
        if not self.allow_empty and not shown.strip():
            ctx.issue(path, "empty", "must not be empty")
        limit = ctx.resolve(self.max)
        if limit is not None and len(shown) > limit:
            ctx.issue(
                path,
                "too_long",
                f"is {len(shown)} characters; the limit is {limit}. Shorten it",
                limit,
                len(shown),
            )
        ctx.chars += len(shown)

    def describe(self, limits: Limits) -> str:
        out = "text or a number" if self.number_ok else "text"
        n = _resolve_static(self.max, limits)
        if n is not None:
            out += f", at most {n} characters"
        if self.multiline:
            out += ", line breaks allowed"
        return out


def _resolve_static(value: int | str | None, limits: Limits) -> int | None:
    if value is None or isinstance(value, int):
        return value
    return int(getattr(limits, value))


def _bad_number(value: int | float) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value) or abs(value) >= _BIG
    return abs(value) >= _BIG


@dataclass(frozen=True)
class Num(Kind):
    """A finite number. `positive` requires more than zero."""

    positive: bool = False

    def check(self, value: Any, path: str, ctx: Ctx) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            ctx.issue(path, "wrong_type", f"expected a number, got {_kind_of(value)}")
        elif _bad_number(value):
            ctx.issue(path, "bad_number", "numbers must be finite and below a quadrillion")
        elif self.positive and value <= 0:
            ctx.issue(path, "bad_number", "must be greater than zero")

    def describe(self, limits: Limits) -> str:
        return "a number greater than zero" if self.positive else "a number"


@dataclass(frozen=True)
class Bool(Kind):
    def check(self, value: Any, path: str, ctx: Ctx) -> None:
        if not isinstance(value, bool):
            ctx.issue(path, "wrong_type", f"expected true or false, got {_kind_of(value)}")

    def describe(self, limits: Limits) -> str:
        return "true or false"


@dataclass(frozen=True, init=False)
class Enum(Kind):
    """One of a fixed list of strings."""

    values: tuple[str, ...]

    def __init__(self, *values: str) -> None:
        if not values or not all(isinstance(v, str) for v in values):
            raise ValueError("Enum needs one or more strings")
        object.__setattr__(self, "values", tuple(values))

    def check(self, value: Any, path: str, ctx: Ctx) -> None:
        if not isinstance(value, str):
            ctx.issue(
                path, "wrong_type", f"expected one of the listed words, got {_kind_of(value)}"
            )
        elif value not in self.values:
            ctx.issue(path, "bad_value", f"must be one of {', '.join(self.values)}")

    def describe(self, limits: Limits) -> str:
        return "one of " + ", ".join(f'"{v}"' for v in self.values)


@dataclass(frozen=True)
class Url(Kind):
    """A web address. `kind` is `link` (a button) or `image` (a picture)."""

    kind: str = "link"

    def __post_init__(self) -> None:
        if self.kind not in ("link", "image"):
            raise ValueError("Url kind must be 'link' or 'image'")

    def limit_names(self) -> list[str]:
        return ["image_url" if self.kind == "image" else "url"]

    def check(self, value: Any, path: str, ctx: Ctx) -> None:
        if not isinstance(value, str):
            ctx.issue(path, "wrong_type", f"expected a web address, got {_kind_of(value)}")
            return
        limit = ctx.limits.image_url if self.kind == "image" else ctx.limits.url
        if len(value) > limit:
            ctx.issue(
                path,
                "too_long",
                f"is {len(value)} characters; the limit is {limit}",
                limit,
                len(value),
            )
            return
        problem = ctx.links.check(value, self.kind)
        if problem:
            ctx.issue(path, problem[0], problem[1])

    def describe(self, limits: Limits) -> str:
        what = "a picture address" if self.kind == "image" else "a web address"
        return f"{what} starting with https://"


@dataclass(frozen=True)
class List(Kind):
    """A list of `of`. `min` counts only when the card is final (a stream may start empty)."""

    of: Kind
    max: int | str | None = None
    min: int = 0

    def limit_names(self) -> list[str]:
        return _names(self.max) + self.of.limit_names()

    def check(self, value: Any, path: str, ctx: Ctx) -> None:
        if not isinstance(value, list):
            ctx.issue(path, "wrong_type", f"expected a list, got {_kind_of(value)}")
            return
        limit = ctx.resolve(self.max)
        if limit is not None and len(value) > limit:
            ctx.issue(
                path,
                "too_many",
                f"has {len(value)} items; the limit is {limit}. Remove some",
                limit,
                len(value),
            )
            return
        if self.min and ctx.mode == "final" and len(value) < self.min:
            ctx.issue(
                path,
                "too_few",
                f"has {len(value)} items; at least {self.min} needed",
                self.min,
                len(value),
            )
        for i, item in enumerate(value):
            self.of.check(item, f"{path}/{i}", ctx)

    def describe(self, limits: Limits) -> str:
        n = _resolve_static(self.max, limits)
        out = f"a list of {self.of.describe(limits)}"
        if n is not None:
            out += f" (at most {n})"
        return out


@dataclass(frozen=True, init=False)
class Obj(Kind):
    """An object with named fields. Wrap a field in `Opt` to make it optional."""

    fields: Mapping[str, Kind | Opt]

    def __init__(self, fields: Mapping[str, Kind | Opt]) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(fields)))

    def limit_names(self) -> list[str]:
        return [n for spec in self.fields.values() for n in _unwrap(spec)[0].limit_names()]

    def check(self, value: Any, path: str, ctx: Ctx) -> None:
        if not isinstance(value, dict):
            ctx.issue(path, "wrong_type", f"expected an object, got {_kind_of(value)}")
            return
        for key in value:
            if key not in self.fields:
                allowed = ", ".join(self.fields) or "none"
                ctx.issue(
                    path + pointer(key),
                    "unknown_key",
                    f"{key!r} is not known here; the keys are: {allowed}",
                )
        for name, spec in self.fields.items():
            kind, required = _unwrap(spec)
            if name in value:
                kind.check(value[name], path + pointer(name), ctx)
            elif required:
                ctx.issue(path + pointer(name), "missing_prop", f"{name!r} is required")

    def describe(self, limits: Limits) -> str:
        parts = []
        for name, spec in self.fields.items():
            kind, required = _unwrap(spec)
            parts.append(f"{name}{'' if required else ' (optional)'}: {kind.describe(limits)}")
        return "an object with " + "; ".join(parts)


@dataclass(frozen=True, init=False)
class Children:
    """Which element types an element may hold, and how many."""

    allowed: tuple[str, ...]
    max: int | str | None = None

    def __init__(self, allowed: tuple[str, ...] | list[str], max: int | str | None = None) -> None:
        object.__setattr__(self, "allowed", tuple(allowed))
        object.__setattr__(self, "max", max)


#: A cross-field check run after an element's props passed the kit. It may assume the props
#: have the right types. Signature: (props, path_of_props, ctx).
PropsCheck = Callable[[dict[str, Any], str, Ctx], None]
