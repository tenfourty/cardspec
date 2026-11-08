# Derived from json-render's spec validation, rewritten in Python; see the NOTICE file.
"""Check a card against a catalogue and report every problem as an `Issue`.

`validate` never raises on a bad card and never changes it. It reads *every* element in
`elements`, reachable from the root or not, so a string cannot hide in an orphan.

Two modes. `final` (the default) is for a finished card. `open` is for a card that is still
being built by a stream of edits: a child key may name an element that has not arrived yet, and
an element may not be attached yet. Every other check is the same in both.
"""

from __future__ import annotations

import contextlib
import re
from collections import deque
from typing import Any

from .catalogue import Catalogue, Element, Profile
from .issue import Issue, pointer
from .limits import Limits
from .links import LinkPolicy
from .schema import Ctx, Full

MAX_ISSUES = 50
_KEY = re.compile(r"[a-z][a-z0-9-]{0,31}")
_ELEMENT_KEYS = ("type", "props", "children")


def validate(
    card: Any,
    *,
    catalogue: Catalogue | None = None,
    limits: Limits | None = None,
    links: LinkPolicy | None = None,
    profile: str | Profile | None = None,
    mode: str = "final",
) -> list[Issue]:
    """Return the issues in `card` (up to 50); an empty list means it is valid.

    `limits` default to the profile's, else to `Limits()`. `links` default to `LinkPolicy()`,
    which allows no pictures. Raises ValueError for an unknown `mode` and KeyError for an
    unknown profile name.
    """
    if mode not in ("final", "open"):
        raise ValueError("mode must be 'final' or 'open'")
    if catalogue is None:
        from .standard import CATALOGUE

        catalogue = CATALOGUE
    prof = catalogue.profile(profile) if isinstance(profile, str) else profile
    ctx = Ctx(
        limits or (prof.limits if prof else Limits()), links or LinkPolicy(), mode, MAX_ISSUES
    )
    with contextlib.suppress(Full):
        _check(card, catalogue, prof, ctx)
    return ctx.issues


def _check(card: Any, cat: Catalogue, prof: Profile | None, ctx: Ctx) -> None:
    if not isinstance(card, dict):
        ctx.issue("", "not_object", "a card must be an object")
        return
    for key in card:
        if key not in ("v", "root", "elements"):
            ctx.issue(
                pointer(key), "unknown_key", f"{key!r} is not known here; use v, root, elements"
            )
    _check_version(card, cat, ctx)
    root = _check_root(card, ctx)
    elements = card.get("elements")
    if "elements" not in card:
        ctx.issue("/elements", "missing_elements", 'the card has no "elements"')
        return
    if not isinstance(elements, dict):
        ctx.issue("/elements", "wrong_type", "elements must be an object keyed by element name")
        return
    if len(elements) > ctx.limits.max_elements:
        ctx.issue(
            "/elements",
            "too_many_elements",
            f"has {len(elements)} elements; the limit is {ctx.limits.max_elements}. Remove some",
            ctx.limits.max_elements,
            len(elements),
        )
        return

    types: dict[str, Element] = {}
    for key, node in elements.items():
        _check_element(key, node, cat, prof, ctx, types)
    if root is not None and root in types and types[root].name != cat.root:
        ctx.issue(
            pointer("elements", root),
            "root_not_card",
            f"the root element must be a {cat.root}, not a {types[root].name}",
        )
    elif root is not None and root in elements and root not in types:
        pass  # its type was unknown or malformed: already reported

    _check_structure(elements, root, cat, ctx, types)
    _check_totals(elements, ctx)


def _check_version(card: dict[str, Any], cat: Catalogue, ctx: Ctx) -> None:
    if "v" not in card:
        ctx.issue("/v", "missing_version", f'the card has no "v"; use "v": {cat.versions[-1]}')
        return
    v = card["v"]
    if isinstance(v, bool) or not isinstance(v, int):
        ctx.issue("/v", "wrong_type", "v must be a whole number")
    elif v not in cat.versions:
        known = ", ".join(str(x) for x in cat.versions)
        ctx.issue(
            "/v", "unsupported_version", f"version {v} is not supported; known versions: {known}"
        )


def _check_root(card: dict[str, Any], ctx: Ctx) -> str | None:
    if "root" not in card:
        ctx.issue("/root", "missing_root", 'the card has no "root" naming its first element')
        return None
    root = card["root"]
    if not isinstance(root, str):
        ctx.issue("/root", "wrong_type", "root must be the key of an element")
        return None
    if not _KEY.fullmatch(root):
        ctx.issue(
            "/root",
            "bad_key",
            "keys use lower-case letters, digits and '-', start with a letter, 32 at most",
        )
        return None
    elements = card.get("elements")
    if isinstance(elements, dict) and root not in elements:
        ctx.issue("/root", "missing_root", f"root names {root!r}, which is not in elements")
        return None
    return root


def _check_element(
    key: str,
    node: Any,
    cat: Catalogue,
    prof: Profile | None,
    ctx: Ctx,
    types: dict[str, Element],
) -> None:
    path = pointer("elements", key)
    if not _KEY.fullmatch(key):
        ctx.issue(
            path,
            "bad_key",
            "keys use lower-case letters, digits and '-', start with a letter, 32 at most",
        )
    if not isinstance(node, dict):
        ctx.issue(path, "wrong_type", "an element must be an object with type, props, children")
        return
    for k in node:
        if k not in _ELEMENT_KEYS:
            ctx.issue(
                f"{path}{pointer(k)}",
                "unknown_key",
                f"{k!r} is not known here; use type, props, children",
            )
    type_name = node.get("type")
    if "type" not in node:
        ctx.issue(path, "missing_type", 'the element has no "type"')
        return
    element = cat.elements.get(type_name) if isinstance(type_name, str) else None
    if element is None:
        known = ", ".join(cat.elements)
        ctx.issue(
            f"{path}/type",
            "unknown_type",
            f"{type_name!r} is not an element type; use one of: {known}",
        )
        return
    types[key] = element
    if prof is not None and prof.elements is not None and element.name not in prof.elements:
        ctx.issue(
            f"{path}/type",
            "element_not_in_profile",
            f"{element.name} cannot be shown on this surface ({prof.name}); remove it",
        )
    props = node.get("props", {})
    before = len(ctx.issues)
    element.schema.check(props, f"{path}/props", ctx)
    if element.check is not None and len(ctx.issues) == before:
        element.check(props, f"{path}/props", ctx)
    children = node.get("children")
    if "children" in node and not isinstance(children, list):
        ctx.issue(f"{path}/children", "wrong_type", "children must be a list of element keys")
    elif element.children is None and children:
        ctx.issue(
            f"{path}/children/0",
            "child_not_allowed",
            f"{element.name} cannot hold children",
        )
    elif element.children is not None and isinstance(children, list):
        limit = ctx.resolve(element.children.max)
        if limit is not None and len(children) > limit:
            ctx.issue(
                f"{path}/children",
                "too_many",
                f"has {len(children)} children; the limit is {limit}",
                limit,
                len(children),
            )


def _check_structure(
    elements: dict[str, Any],
    root: str | None,
    cat: Catalogue,
    ctx: Ctx,
    types: dict[str, Element],
) -> None:
    edges: dict[str, list[str]] = {}
    parent: dict[str, str] = {}
    for key, node in elements.items():
        children = node.get("children") if isinstance(node, dict) else None
        if not isinstance(children, list) or key not in types:
            continue
        element = types[key]
        seen: set[str] = set()
        for i, child in enumerate(children):
            cpath = f"{pointer('elements', key)}/children/{i}"
            if not isinstance(child, str):
                ctx.issue(cpath, "wrong_type", "a child must be the key of an element")
                continue
            if child in seen or (child in parent and parent[child] != key):
                ctx.issue(
                    cpath,
                    "duplicate_child",
                    f"{child!r} is already used; an element can be placed in one spot only",
                )
                if child in elements:
                    edges.setdefault(key, []).append(child)
                continue
            seen.add(child)
            parent[child] = key
            if child not in elements:
                if ctx.mode == "final":
                    ctx.issue(cpath, "missing_child", f"{child!r} is not in elements")
                continue
            edges.setdefault(key, []).append(child)
            if (
                element.children is not None
                and child in types
                and types[child].name not in element.children.allowed
            ):
                allowed = ", ".join(element.children.allowed)
                ctx.issue(
                    cpath,
                    "child_not_allowed",
                    f"{element.name} cannot hold a {types[child].name}; it takes: {allowed}",
                )
    _check_cycles(edges, ctx)
    if root is None or root not in elements:
        return
    depth = {root: 1}
    queue = deque([root])
    reported = False
    while queue:
        key = queue.popleft()
        for child in edges.get(key, []):
            if child in depth:
                continue
            depth[child] = depth[key] + 1
            if depth[child] > ctx.limits.max_nesting and not reported:
                reported = True
                idx = elements[key]["children"].index(child)
                ctx.issue(
                    f"{pointer('elements', key)}/children/{idx}",
                    "too_deep",
                    f"is nested {depth[child]} levels deep; the limit is {ctx.limits.max_nesting}",
                    ctx.limits.max_nesting,
                    depth[child],
                )
            queue.append(child)
    if ctx.mode == "final":
        for key in elements:
            if key not in depth:
                ctx.issue(
                    pointer("elements", key),
                    "orphaned_element",
                    "is not reachable from the root; attach it to a parent or remove it",
                )


def _check_cycles(edges: dict[str, list[str]], ctx: Ctx) -> None:
    state: dict[str, int] = {}  # 1 = on the current path, 2 = finished
    for start in edges:
        if start in state:
            continue
        stack = [(start, iter(edges.get(start, [])))]
        state[start] = 1
        while stack:
            node, it = stack[-1]
            for child in it:
                if state.get(child) == 1:
                    idx = edges[node].index(child)
                    ctx.issue(
                        f"{pointer('elements', node)}/children/{idx}",
                        "cycle",
                        f"{child!r} contains {node!r}, which contains it again; remove the loop",
                    )
                elif child not in state:
                    state[child] = 1
                    stack.append((child, iter(edges.get(child, []))))
                    break
            else:
                state[node] = 2
                stack.pop()


def _check_totals(elements: dict[str, Any], ctx: Ctx) -> None:
    counts: dict[str, list[str]] = {}
    for key, node in elements.items():
        if isinstance(node, dict) and isinstance(node.get("type"), str):
            counts.setdefault(node["type"], []).append(key)
    for type_name, cap in ctx.limits.max_per_type.items():
        keys = counts.get(type_name, [])
        if len(keys) > cap:
            ctx.issue(
                pointer("elements", keys[cap]),
                "too_many_of_type",
                f"a card holds at most {cap} {type_name}; this one has {len(keys)}",
                cap,
                len(keys),
            )
    if ctx.chars > ctx.limits.max_chars:
        ctx.issue(
            "",
            "too_many_chars",
            f"the card holds {ctx.chars} characters of text; the limit is {ctx.limits.max_chars}. "
            "Cut some text",
            ctx.limits.max_chars,
            ctx.chars,
        )
