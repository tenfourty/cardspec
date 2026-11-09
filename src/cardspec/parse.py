"""Turn what someone wrote into the canonical (flat) card, safely.

Input may be JSON text (str or bytes) or an already-decoded dict. The size and the depth are
checked before anything walks the data; duplicate keys, NaN and Infinity are refused.

Two shapes are accepted:

* the flat form: `{"v": 1, "root": "card", "elements": {"<key>": {"type", "props", "children"}}}`
* the nested form, for a card written in one go: `{"type": "Card", "v": 1, "title": ...,
  "children": [{"type": "Text", "content": ...}]}`, with props at the top level of each element.
  It is converted once, here, to the flat form with generated keys.

`parse` does not know the catalogue and does not check props; `validate` does that.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .issue import CardError, Issue, pointer
from .limits import Limits

_MAX_ISSUES = 50


class _Stop(Exception):
    pass


def _fail(path: str, code: str, message: str, **kw: int) -> CardError:
    return CardError([Issue(path, code, message, kw.get("limit"), kw.get("actual"))])


def _scan_depth(text: str, limit: int) -> None:
    """Refuse text whose brackets nest deeper than `limit`, without building anything."""
    depth = 0
    in_string = False
    escaped = False
    for c in text:
        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
        elif c == '"':
            in_string = True
        elif c in "[{":
            depth += 1
            if depth > limit:
                raise _fail("", "json_too_deep", f"nests deeper than {limit} levels", limit=limit)
        elif c in "]}":
            depth -= 1


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise _fail("", "duplicate_key", f"the key {key!r} appears twice in one object")
        out[key] = value
    return out


def _constant(name: str) -> Any:
    raise _fail("", "bad_number", f"{name} is not a number a card can hold")


def _float(text: str) -> float:
    value = float(text)
    if value != value or value in (float("inf"), float("-inf")):
        raise _fail("", "bad_number", "a number is too large to hold")
    return value


def _copy_checked(value: Any, path: str, depth: int, limit: int) -> Any:
    """Copy decoded data, refusing anything JSON cannot hold or that nests too deeply."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise _fail(path, "bad_number", "a number must be finite")
        return value
    if isinstance(value, (list, dict)):
        if depth >= limit:
            raise _fail("", "json_too_deep", f"nests deeper than {limit} levels", limit=limit)
        if isinstance(value, list):
            return [_copy_checked(v, f"{path}/{i}", depth + 1, limit) for i, v in enumerate(value)]
        out: dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise _fail(path, "wrong_type", "object keys must be text")
            out[k] = _copy_checked(v, path + pointer(k), depth + 1, limit)
        return out
    raise _fail(path, "wrong_type", f"{type(value).__name__} is not a JSON value")


def _load(raw: Any, limits: Limits) -> Any:
    if isinstance(raw, (bytes, bytearray)):
        if len(raw) > limits.max_bytes:
            raise _fail(
                "",
                "too_large",
                f"is {len(raw)} bytes; the limit is {limits.max_bytes}",
                limit=limits.max_bytes,
                actual=len(raw),
            )
        try:
            raw = bytes(raw).decode("utf-8")
        except UnicodeDecodeError:
            raise _fail("", "bad_encoding", "is not valid UTF-8 text") from None
    if isinstance(raw, str):
        # Characters are at most 4 bytes each, so a short string cannot be over the limit.
        if len(raw) > limits.max_bytes:
            raise _fail(
                "",
                "too_large",
                f"is {len(raw)} characters; the limit is {limits.max_bytes} bytes",
                limit=limits.max_bytes,
                actual=len(raw),
            )
        try:
            size = len(raw.encode("utf-8"))
        except UnicodeEncodeError:
            raise _fail("", "bad_encoding", "holds characters that cannot be encoded") from None
        if size > limits.max_bytes:
            raise _fail(
                "",
                "too_large",
                f"is {size} bytes; the limit is {limits.max_bytes}",
                limit=limits.max_bytes,
                actual=size,
            )
        _scan_depth(raw, limits.max_json_depth)
        try:
            return json.loads(
                raw, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float
            )
        except CardError:
            raise
        except RecursionError:
            raise _fail("", "json_too_deep", "nests too deeply") from None
        except ValueError as e:
            raise _fail("", "bad_json", f"is not valid JSON ({e})") from None
    data = _copy_checked(raw, "", 0, limits.max_json_depth)
    try:
        size = len(json.dumps(data, ensure_ascii=False).encode("utf-8", "surrogatepass"))
    except ValueError:
        raise _fail("", "bad_number", "holds a number that is too large") from None
    if size > limits.max_bytes:
        raise _fail(
            "",
            "too_large",
            f"is {size} bytes as JSON; the limit is {limits.max_bytes}",
            limit=limits.max_bytes,
            actual=size,
        )
    return data


def _key_for(type_name: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9-]", "", type_name.lower())[:26]
    if not base or not base[0].isalpha():
        base = "el" + base
    key, n = base, 1
    while key in taken:
        n += 1
        key = f"{base}-{n}"
    taken.add(key)
    return key


def _from_nested(root: dict[str, Any], limits: Limits) -> dict[str, Any]:
    issues: list[Issue] = []
    elements: dict[str, Any] = {}

    def add(node: Any, path: str, is_root: bool) -> str | None:
        if not isinstance(node, dict):
            issues.append(Issue(path, "wrong_type", 'each child must be an object with a "type"'))
            return None
        type_name = node.get("type")
        if not isinstance(type_name, str) or not type_name:
            issues.append(Issue(path, "missing_type", 'this element has no "type" (a text name)'))
            return None
        if len(elements) >= limits.max_elements:
            issues.append(
                Issue(
                    "",
                    "too_many_elements",
                    f"has more than {limits.max_elements} elements",
                    limits.max_elements,
                )
            )
            raise _Stop
        key = _key_for(type_name, set(elements))
        skip = {"type", "children"} | ({"v"} if is_root else set())
        element: dict[str, Any] = {
            "type": type_name,
            "props": {k: v for k, v in node.items() if k not in skip},
        }
        elements[key] = element
        if "children" in node:
            children = node["children"]
            if not isinstance(children, list):
                issues.append(Issue(f"{path}/children", "wrong_type", "children must be a list"))
            else:
                keys: list[str] = []
                for i, child in enumerate(children):
                    child_key = add(child, f"{path}/children/{i}", False)
                    if child_key is not None:
                        keys.append(child_key)
                element["children"] = keys
        return key

    try:
        root_key = add(root, "", True)
    except _Stop:
        root_key = None
    if issues:
        raise CardError(issues[:_MAX_ISSUES])
    card: dict[str, Any] = {}
    if "v" in root:
        card["v"] = root["v"]
    card["root"] = root_key
    card["elements"] = elements
    return card


def parse(raw: str | bytes | dict[str, Any], *, limits: Limits | None = None) -> dict[str, Any]:
    """Return the canonical flat card for `raw`, or raise `CardError`.

    The input is never changed. A parsed card is not yet valid: call `validate` on it.
    """
    limits = limits or Limits()
    data = _load(raw, limits)
    if not isinstance(data, dict):
        raise _fail("", "not_object", "a card must be a JSON object")
    if "elements" in data or "root" in data:
        return data
    if "type" in data:
        return _from_nested(data, limits)
    raise _fail(
        "",
        "unknown_form",
        'a card is either {"v", "root", "elements"} or an element with a "type" such as "Card"',
    )
