"""Seeded random damage to a valid card: validate must report, never raise, and stay bounded."""

from __future__ import annotations

import copy
import json
import random

from cardspec import CardError, Issue, parse, validate

from .conftest import NESTED_EXAMPLE

NASTY = [
    None,
    True,
    0,
    -1,
    1.5,
    10**30,
    float("nan"),
    float("inf"),
    "",
    " ",
    "x" * 5000,
    "<@U123>",
    "<!here>",
    "@here",
    "`*&]]>",
    "‮",
    "​",
    "\x00",
    "a\nb",
    [],
    {},
    [[]],
    {"a": 1},
    ["x"] * 100,
    "https://example.com",
    "javascript:alert(1)",
    "../",
    "\ud800",
]


def paths(node, prefix=()):
    yield prefix
    if isinstance(node, dict):
        for k, v in node.items():
            yield from paths(v, (*prefix, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from paths(v, (*prefix, i))


def test_random_damage_never_raises():
    rng = random.Random(20261108)
    base = parse(NESTED_EXAMPLE)
    for _ in range(600):
        card = copy.deepcopy(base)
        for _ in range(rng.randint(1, 4)):
            target = rng.choice([p for p in paths(card) if p])
            parent = card
            for step in target[:-1]:
                parent = parent[step]
            action = rng.random()
            if action < 0.2 and isinstance(parent, dict):
                del parent[target[-1]]
            elif action < 0.3 and isinstance(parent, dict):
                parent[rng.choice(["k", "type", "props", "children", "\u202e"])] = copy.deepcopy(
                    rng.choice(NASTY)
                )
            else:
                parent[target[-1]] = copy.deepcopy(rng.choice(NASTY))
        for mode in ("final", "open"):
            issues = validate(card, mode=mode)
            assert len(issues) <= 50
            assert all(isinstance(i, Issue) for i in issues)
            for issue in issues:
                assert issue.path == "" or issue.path.startswith("/")
            try:
                json.dumps([i.to_dict() for i in issues])
            except (TypeError, ValueError) as e:  # pragma: no cover
                raise AssertionError(f"issue not serialisable: {issues}") from e


def test_random_text_never_crashes_parse():
    rng = random.Random(7)
    alphabet = '{}[]",:\\ \n0123456789eE.-+truefalsnNaIityé‮'
    for _ in range(500):
        raw = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 80)))
        try:
            parse(raw)
        except CardError as e:
            assert e.issues
