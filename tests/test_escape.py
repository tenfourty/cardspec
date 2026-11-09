from __future__ import annotations

import pytest

from cardspec import LinkPolicy, escape_mrkdwn, parse, validate


@pytest.mark.parametrize(
    ("raw", "safe"),
    [
        ("<https://x|y>", "&lt;https://x|y&gt;"),
        ("<@U123> <!here>", "&lt;@U123&gt; &lt;!here&gt;"),
        ("a & b", "a &amp; b"),
        ("&lt;", "&amp;lt;"),
        ("plain", "plain"),
    ],
)
def test_escape_leaves_no_angle_bracket(raw, safe):
    assert escape_mrkdwn(raw) == safe
    assert "<" not in safe and ">" not in safe


def test_validate_accepts_markup_characters_so_the_renderer_must_escape():
    # Pins the contract in the README: the checker does not refuse these characters, so
    # escaping them is the renderer's job.
    card = {
        "type": "Card",
        "v": 1,
        "title": "t <!here> & <https://x|y>",
        "children": [{"type": "Text", "content": "<@U123>"}],
    }
    assert validate(parse(card), links=LinkPolicy()) == []
