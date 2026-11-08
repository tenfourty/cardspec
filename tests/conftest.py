from __future__ import annotations

import copy
from typing import Any

import pytest

# The worked example from the format description, in the nested writing form.
NESTED_EXAMPLE: dict[str, Any] = {
    "type": "Card",
    "v": 1,
    "title": "Deploy: web 2026.11.8",
    "subtitle": "Finished 14:02, 3 minutes",
    "children": [
        {"type": "Text", "content": "**Healthy.** All checks passed; one slow migration."},
        {
            "type": "Fields",
            "items": [
                {"label": "Version", "value": "2026.11.8"},
                {"label": "Errors (1h)", "value": 0},
                {"label": "p95 latency", "value": "212 ms"},
                {"label": "Rollback ready", "value": "yes"},
            ],
        },
        {
            "type": "Table",
            "headers": ["Step", "Result", "Seconds"],
            "rows": [["build", "ok", 61], ["migrate", "ok (slow)", 94], ["smoke", "ok", 12]],
            "align": ["left", "left", "right"],
        },
        {
            "type": "Chart",
            "title": "Errors per hour",
            "kind": "bar",
            "categories": ["12", "13", "14"],
            "series": [{"name": "errors", "values": [2, 1, 0]}],
        },
        {"type": "Divider"},
        {
            "type": "Actions",
            "buttons": [{"label": "Open dashboard", "url": "https://dash.example.com/web"}],
        },
    ],
}


def small_card() -> dict[str, Any]:
    """The smallest valid card, in the flat form."""
    return {
        "v": 1,
        "root": "card",
        "elements": {
            "card": {"type": "Card", "props": {"title": "Hello"}, "children": ["note"]},
            "note": {"type": "Text", "props": {"content": "Hi there."}},
        },
    }


@pytest.fixture
def card() -> dict[str, Any]:
    return small_card()


@pytest.fixture
def nested() -> dict[str, Any]:
    return copy.deepcopy(NESTED_EXAMPLE)


def codes(issues: list[Any]) -> list[str]:
    return [i.code for i in issues]
