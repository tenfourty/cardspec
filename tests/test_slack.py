from __future__ import annotations

import json
from typing import Any

import pytest

from cardspec import Limits, LinkPolicy, escape_mrkdwn, parse, render_slack, validate
from cardspec.slack import SlackResult

ZW = "​"


def card_of(*children: dict[str, Any], title: str = "Title", **extra: Any) -> dict[str, Any]:
    return {"type": "Card", "v": 1, "title": title, "children": list(children), **extra}


def render(*children: dict[str, Any], **kw: Any) -> SlackResult:
    title = kw.pop("title", "Title")
    return render_slack(card_of(*children, title=title), **kw)


def codes(result: SlackResult) -> list[str]:
    return [i.code for i in result.issues]


def body(result: SlackResult) -> list[dict[str, Any]]:
    """The blocks after the title block."""
    assert result.ok, result.issues
    return result.blocks[1:]


def all_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in all_strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in all_strings(v)]
    return []


# ---- the parts -------------------------------------------------------------------------------


def test_card_title_and_subtitle():
    r = render_slack(card_of(title="Deploy", subtitle="Done at 14:02"))
    assert r.ok
    assert r.blocks[0] == {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "*Deploy*", "verbatim": True},
    }
    assert r.blocks[1] == {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "Done at 14:02", "verbatim": True}],
    }
    assert r.text == "Deploy"


def test_accepts_the_flat_form_too(card):
    r = render_slack(card)
    assert r.ok
    assert r.blocks[1]["text"]["text"] == "Hi there."


def test_text_plain_bold_italic_code():
    (b,) = body(render({"type": "Text", "content": "a **bold** _it_ and `co_de` end"}))
    assert b == {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "a *bold* _it_ and `co_de` end", "verbatim": True},
    }


def test_text_style_bold_and_muted():
    (b,) = body(render({"type": "Text", "content": "Loud\nsecond", "style": "bold"}))
    assert b["text"]["text"] == "*Loud*\n*second*"
    (m,) = body(render({"type": "Text", "content": "quiet", "style": "muted"}))
    assert m == {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "quiet", "verbatim": True}],
    }


def test_section_title_then_children_flattened():
    blocks = body(
        render(
            {
                "type": "Section",
                "title": "Checks",
                "children": [{"type": "Text", "content": "ok"}, {"type": "Divider"}],
            }
        )
    )
    assert blocks[0]["text"]["text"] == "*Checks*"
    assert blocks[1]["text"]["text"] == "ok"
    assert blocks[2] == {"type": "divider"}


def test_section_without_title_adds_no_heading():
    blocks = body(render({"type": "Section", "children": [{"type": "Divider"}]}))
    assert blocks == [{"type": "divider"}]


def test_fields():
    (b,) = body(
        render(
            {
                "type": "Fields",
                "items": [{"label": "Errors", "value": 0}, {"label": "Note", "value": ""}],
            }
        )
    )
    assert b == {
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": "*Errors*\n0", "verbatim": True},
            {"type": "mrkdwn", "text": "*Note*", "verbatim": True},
        ],
    }


def test_table_header_rows_align_and_caption():
    blocks = body(
        render(
            {
                "type": "Table",
                "headers": ["Step", "Seconds"],
                "rows": [["build", 61], ["smoke", 1.5]],
                "align": ["left", "right"],
                "caption": "Timings",
            }
        )
    )
    table, caption = blocks
    assert table["type"] == "table"
    assert table["rows"] == [
        [{"type": "raw_text", "text": "Step"}, {"type": "raw_text", "text": "Seconds"}],
        [{"type": "raw_text", "text": "build"}, {"type": "raw_text", "text": "61"}],
        [{"type": "raw_text", "text": "smoke"}, {"type": "raw_text", "text": "1.5"}],
    ]
    assert table["column_settings"] == [{"align": "left"}, {"align": "right"}]
    assert caption["type"] == "context"


def test_table_without_align_has_no_column_settings():
    (t,) = body(render({"type": "Table", "headers": ["a"], "rows": [["x"]]}))
    assert "column_settings" not in t


def test_divider():
    assert body(render({"type": "Divider"})) == [{"type": "divider"}]


def test_actions_are_link_buttons_with_an_action_id_for_the_acknowledgement():
    (b,) = body(
        render(
            {
                "type": "Actions",
                "buttons": [{"label": "Open", "url": "https://dash.example.com/web"}],
            }
        )
    )
    assert b["type"] == "actions"
    (button,) = b["elements"]
    action_id = button.pop("action_id")
    assert button == {
        "type": "button",
        "text": {"type": "plain_text", "text": "Open", "emoji": False},
        "url": "https://dash.example.com/web",
    }
    assert action_id == "cardspec-link-actions-0"
    assert "value" not in button


def test_each_link_button_has_its_own_stable_action_id():
    two = {
        "type": "Actions",
        "buttons": [
            {"label": "a", "url": "https://a.example.com/x"},
            {"label": "b", "url": "https://a.example.com/y"},
        ],
    }
    ids = [e["action_id"] for e in body(render(two, two))[0]["elements"]]
    again = [e["action_id"] for e in body(render(two, two))[0]["elements"]]
    assert ids == again and len(set(ids)) == 2
    other = [e["action_id"] for e in body(render(two, two))[1]["elements"]]
    assert not set(ids) & set(other)
    assert all(len(i) <= 255 for i in ids + other)


def chart(kind: str = "bar", **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"type": "Chart", "title": "Errors", "kind": kind}
    if kind == "pie":
        base["segments"] = [{"label": "a", "value": 2}, {"label": "b", "value": 1.5}]
    else:
        base["categories"] = ["12", "13"]
        base["series"] = [
            {"name": "errors", "values": [2, -1]},
            {"name": "warnings", "values": [0, 3]},
        ]
    return {**base, **kw}


@pytest.mark.parametrize("kind", ["bar", "line", "area"])
def test_chart_with_series(kind):
    (b,) = body(render(chart(kind)))
    assert b == {
        "type": "data_visualization",
        "title": "Errors",
        "chart": {
            "type": kind,
            "series": [
                {
                    "name": "errors",
                    "data": [{"label": "12", "value": 2}, {"label": "13", "value": -1}],
                },
                {
                    "name": "warnings",
                    "data": [{"label": "12", "value": 0}, {"label": "13", "value": 3}],
                },
            ],
            "axis_config": {"categories": ["12", "13"]},
        },
    }


def test_pie_chart():
    (b,) = body(render(chart("pie")))
    assert b == {
        "type": "data_visualization",
        "title": "Errors",
        "chart": {
            "type": "pie",
            "segments": [{"label": "a", "value": 2}, {"label": "b", "value": 1.5}],
        },
    }


def test_chart_text_is_not_escaped_and_is_measured_raw():
    label = "R&D <> Q&A ops"  # 14 characters; entity-escaped it would be 26
    assert len(label) == 14
    (b,) = body(
        render(
            chart(
                "bar",
                title="<!here> & *x*",
                categories=[label],
                series=[{"name": label, "values": [1]}],
            )
        )
    )
    assert b["title"] == "<!here> & *x*"
    assert b["chart"]["axis_config"]["categories"] == [label]
    assert b["chart"]["series"][0]["name"] == label
    assert b["chart"]["series"][0]["data"][0]["label"] == label
    (p,) = body(render(chart("pie", segments=[{"label": label, "value": 1}])))
    assert p["chart"]["segments"][0]["label"] == label


BIG = Limits(
    chart_label=100,
    chart_categories=60,
    chart_series=20,
    title=500,
    max_chars=9000,
    max_elements=100,
)


def chart_issues(**kw: Any) -> list[str]:
    return codes(render_slack(card_of(chart(**kw)), limits=BIG))


def test_chart_limits_are_refused():
    assert chart_issues(title="t" * 51) == ["slack_text_too_long"]
    assert chart_issues(categories=["c" * 21, "d"]) == ["slack_text_too_long"]
    assert chart_issues(series=[{"name": "n" * 21, "values": [1, 2]}]) == ["slack_text_too_long"]
    cats = [str(i) for i in range(21)]
    assert chart_issues(categories=cats, series=[{"name": "s", "values": [1] * 21}]) == [
        "slack_chart_too_large"
    ]
    series = [{"name": f"s{i}", "values": [1, 2]} for i in range(13)]
    assert chart_issues(series=series) == ["slack_chart_too_large"]
    segs = [{"label": str(i), "value": 1} for i in range(13)]
    assert chart_issues(kind="pie", segments=segs) == ["slack_chart_too_large"]


def test_chart_at_the_limits_renders():
    cats = [f"{i:020d}" for i in range(20)]
    series = [{"name": f"{i:020d}", "values": [1] * 20} for i in range(12)]
    r = render_slack(card_of(chart(categories=cats, series=series, title="t" * 50)), limits=BIG)
    assert r.ok, r.issues
    segs = [{"label": str(i), "value": 1} for i in range(12)]
    r = render_slack(card_of(chart("pie", segments=segs)), limits=BIG)
    assert r.ok, r.issues


def test_chart_series_names_and_categories_must_be_unique():
    dup = [{"name": "same", "values": [1, 2]}, {"name": "same", "values": [3, 4]}]
    assert chart_issues(series=dup) == ["slack_chart_names_not_unique"]
    assert chart_issues(categories=["a", "a"]) == ["slack_chart_names_not_unique"]


def test_at_most_two_charts_per_message():
    r = render_slack(card_of(chart(), chart(), chart()), limits=Limits(max_per_type={"Chart": 5}))
    assert codes(r) == ["slack_too_many_charts"]
    assert render_slack(card_of(chart(), chart()), limits=Limits(max_per_type={"Chart": 5})).ok


def test_the_worked_example_renders(nested):
    r = render_slack(nested)
    assert r.ok
    assert [b["type"] for b in r.blocks] == [
        "section",
        "context",
        "section",
        "section",
        "table",
        "data_visualization",
        "divider",
        "actions",
    ]
    json.dumps(r.blocks)


def text_objects(value: Any) -> list[dict[str, Any]]:
    """Every dict that is a Slack text object (it has a `type` of mrkdwn or plain_text)."""
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("type") in ("mrkdwn", "plain_text"):
            found.append(value)
        for v in value.values():
            found += text_objects(v)
    elif isinstance(value, list):
        for v in value:
            found += text_objects(v)
    return found


def test_every_mrkdwn_object_is_verbatim_and_plain_text_is_not(nested):
    r = render_slack(nested)
    assert r.ok
    objs = text_objects(r.blocks)
    kinds = {o["type"] for o in objs}
    assert "mrkdwn" in kinds
    for o in objs:
        if o["type"] == "mrkdwn":
            assert o["verbatim"] is True, o
        else:
            assert "verbatim" not in o, o


def test_each_part_that_emits_mrkdwn_is_verbatim():
    card = card_of(
        {"type": "Text", "content": "see https://dash.example.com and #general"},
        {"type": "Section", "title": "S", "children": [{"type": "Text", "content": "x"}]},
        {"type": "Fields", "items": [{"label": "A", "value": "b"}]},
        subtitle="sub",
    )
    r = render_slack(card)
    assert r.ok
    mrkdwn = [o for o in text_objects(r.blocks) if o["type"] == "mrkdwn"]
    assert len(mrkdwn) >= 6
    assert all(o["verbatim"] is True for o in mrkdwn)


# ---- pictures --------------------------------------------------------------------------------

IMG = {"type": "Image", "url": "https://img.example.com/a.png", "alt": "A chart"}


def test_picture_refused_without_a_host_list():
    r = render(IMG)
    assert not r.ok and r.blocks == []
    assert codes(r) == ["image_host_not_allowed"]


def test_picture_refused_from_an_unlisted_host_and_over_http():
    r = render(IMG, links=LinkPolicy(image_hosts=["other.example.com"]))
    assert codes(r) == ["image_host_not_allowed"]
    r = render(
        {"type": "Image", "url": "http://img.example.com/a.png", "alt": "x"},
        links=LinkPolicy(image_hosts=["img.example.com"]),
    )
    assert codes(r) == ["bad_url"]


def test_picture_from_a_listed_host_renders():
    (b,) = body(render(IMG, links=LinkPolicy(image_hosts=["img.example.com"])))
    assert b == {
        "type": "image",
        "image_url": "https://img.example.com/a.png",
        "alt_text": "A chart",
    }


# ---- escaping --------------------------------------------------------------------------------

NASTY = [
    "*bold* _it_ ~gone~ `code`",
    "<@U123> <!channel> <!here> <#C123>",
    "<https://evil.example.com|click> & more",
    "a &amp; b &lt;",
    "```block```",
]


def _no_live_markup(s: str) -> None:
    assert "<" not in s and ">" not in s, s
    assert "&" not in s.replace("&amp;", "").replace("&lt;", "").replace("&gt;", ""), s


@pytest.mark.parametrize("nasty", NASTY)
def mrkdwn_strings(value: Any) -> list[str]:
    """Every string that Slack reads as mrkdwn."""
    if isinstance(value, dict):
        if value.get("type") == "mrkdwn":
            return [value["text"]]
        return [s for v in value.values() for s in mrkdwn_strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in mrkdwn_strings(v)]
    return []


@pytest.mark.parametrize("nasty", NASTY)
def test_every_mrkdwn_string_and_the_fallback_are_escaped(nasty):
    r = render_slack(
        card_of(
            {"type": "Section", "title": nasty, "children": [{"type": "Text", "content": nasty}]},
            {"type": "Text", "content": nasty, "style": "muted"},
            {"type": "Fields", "items": [{"label": nasty, "value": nasty}]},
            {"type": "Table", "headers": [nasty], "rows": [[nasty]], "caption": nasty},
            title=nasty,
            subtitle=nasty,
        )
    )
    assert r.ok, r.issues
    found = mrkdwn_strings(r.blocks)
    assert len(found) == 7
    for s in [*found, r.text]:
        _no_live_markup(s)


@pytest.mark.parametrize("nasty", NASTY)
def test_plain_text_places_show_the_text_as_typed(nasty):
    r = render_slack(
        card_of(
            {"type": "Table", "headers": [nasty], "rows": [[nasty]]},
            {"type": "Actions", "buttons": [{"label": nasty, "url": "https://a.example.com/x"}]},
            {"type": "Image", "url": "https://img.example.com/a.png", "alt": nasty},
            chart("pie", title=nasty, segments=[{"label": nasty[:20], "value": 1}]),
        ),
        links=LinkPolicy(image_hosts=["img.example.com"]),
        limits=Limits(cell=200, alt=200, button_label=40, title=150),
    )
    assert r.ok, r.issues
    table, actions, image, viz = r.blocks[1:]
    assert table["rows"] == [[{"type": "raw_text", "text": nasty}]] * 2
    assert actions["elements"][0]["text"]["text"] == nasty
    assert image["alt_text"] == nasty
    assert viz["title"] == nasty and viz["chart"]["segments"][0]["label"] == nasty[:20]


def test_a_mention_or_link_in_text_cannot_form():
    (b,) = body(render({"type": "Text", "content": "<@U123> <!channel> <https://x.example.com|y>"}))
    text = b["text"]["text"]
    assert "<" not in text and ">" not in text
    assert text.startswith(escape_mrkdwn("<@U123>"))


def test_markup_characters_in_plain_strings_are_defused():
    (b,) = body(render({"type": "Fields", "items": [{"label": "*x*", "value": "_y_ ~z~ `w`"}]}))
    label, value = b["fields"][0]["text"].split("\n")
    for chars in (label[1:-1], value):
        for mark in "*_~`":
            # every markup character is followed by a zero-width space, so it cannot pair up
            assert chars.count(mark) == chars.count(mark + ZW)


def test_code_span_content_is_escaped_but_not_defused():
    (b,) = body(render({"type": "Text", "content": "`<@U1> & *x*`"}))
    assert b["text"]["text"] == "`&lt;@U1&gt; &amp; *x*`"


def test_markup_inside_bold_does_not_break_out():
    (b,) = body(render({"type": "Text", "content": "**a <!here> b**"}))
    assert b["text"]["text"] == "*a &lt;!here&gt; b*"


# ---- limits: refused, never truncated ---------------------------------------------------------


def test_too_many_blocks_is_refused():
    many = [{"type": "Divider"} for _ in range(50)]
    limits = Limits(max_elements=100, max_nesting=3)
    r = render_slack(card_of(*many), limits=limits)
    assert not r.ok and r.blocks == []
    assert codes(r) == ["slack_too_many_blocks"]
    assert r.issues[0].limit == 50 and r.issues[0].actual == 51


def test_exactly_fifty_blocks_is_fine():
    r = render_slack(
        card_of(*[{"type": "Divider"} for _ in range(49)]), limits=Limits(max_elements=100)
    )
    assert r.ok and len(r.blocks) == 50


def test_section_text_over_3000_is_refused_even_when_the_card_limit_allows_it():
    r = render_slack(
        card_of({"type": "Text", "content": "x" * 3001}), limits=Limits(text=5000, max_chars=9000)
    )
    assert codes(r) == ["slack_text_too_long"]
    assert r.issues[0].limit == 3000 and r.issues[0].actual == 3001


def test_escaping_that_makes_text_too_long_is_refused():
    r = render_slack(
        card_of({"type": "Text", "content": "&" * 700}), limits=Limits(text=5000, max_chars=9000)
    )
    assert codes(r) == ["slack_text_too_long"]


def test_context_text_limit():
    r = render_slack(
        card_of({"type": "Text", "content": "y" * 3001, "style": "muted"}),
        limits=Limits(text=5000, max_chars=9000),
    )
    assert codes(r) == ["slack_text_too_long"]


def test_title_over_3000_is_refused():
    r = render_slack(card_of(title="t" * 3001), limits=Limits(title=5000, max_chars=9000))
    assert codes(r) == ["slack_text_too_long"]


def test_too_many_fields_in_one_section():
    items = [{"label": f"l{i}", "value": i} for i in range(11)]
    r = render_slack(card_of({"type": "Fields", "items": items}), limits=Limits(fields_items=50))
    assert codes(r) == ["slack_too_many_fields"]
    assert r.issues[0].limit == 10 and r.issues[0].actual == 11


def test_field_text_over_2000_is_refused():
    r = render_slack(
        card_of({"type": "Fields", "items": [{"label": "l", "value": "v" * 2100}]}),
        limits=Limits(field_value=3000, max_chars=9000),
    )
    assert codes(r) == ["slack_text_too_long"]


def test_table_row_and_column_limits():
    big = Limits(table_rows=200, table_cols=30, max_chars=100000, max_bytes=10**6)
    rows = [["x"] for _ in range(100)]  # 100 rows plus the header row is 101
    r = render_slack(card_of({"type": "Table", "headers": ["h"], "rows": rows}), limits=big)
    assert codes(r) == ["slack_table_too_large"]
    assert r.issues[0].limit == 100 and r.issues[0].actual == 101
    r = render_slack(
        card_of({"type": "Table", "headers": ["h"] * 21, "rows": [["x"] * 21]}), limits=big
    )
    assert codes(r) == ["slack_table_too_large"]
    assert r.issues[0].limit == 20
    ok = render_slack(
        card_of({"type": "Table", "headers": ["h"] * 20, "rows": [["x"] * 20] * 99}), limits=big
    )
    assert ok.ok


TABLE_LIMITS = Limits(
    table_rows=200, cell=1000, max_chars=100000, max_bytes=10**6, max_per_type={"Table": 3}
)


def test_table_characters_are_counted_across_all_cells():
    rows = [["x" * 101] for _ in range(99)]  # 99 * 101 + the 1-character header = 10000
    ok = render_slack(
        card_of({"type": "Table", "headers": ["h"], "rows": rows}), limits=TABLE_LIMITS
    )
    assert ok.ok, ok.issues
    rows[0] = ["x" * 102]
    r = render_slack(
        card_of({"type": "Table", "headers": ["h"], "rows": rows}), limits=TABLE_LIMITS
    )
    assert codes(r) == ["slack_table_too_large"]
    assert r.issues[0].limit == 10000 and r.issues[0].actual == 10001


def test_table_characters_are_measured_on_the_raw_text():
    rows = [["&" * 100] for _ in range(99)]  # 9900 raw; 49500 if entity-escaped
    r = render_slack(
        card_of({"type": "Table", "headers": ["h"], "rows": rows}), limits=TABLE_LIMITS
    )
    assert r.ok, r.issues


def test_table_characters_are_counted_across_tables_in_one_message():
    rows = [["x" * 100] for _ in range(60)]  # 6001 with the header, twice
    t = {"type": "Table", "headers": ["h"], "rows": rows}
    r = render_slack(card_of(t, t), limits=TABLE_LIMITS)
    assert codes(r) == ["slack_table_too_large"]
    assert r.issues[0].path == "" and r.issues[0].actual == 12002


def test_several_tables_are_fine_when_the_card_limits_allow_them():
    t = {"type": "Table", "headers": ["h"], "rows": [["x"]]}
    assert render_slack(card_of(t, t), limits=TABLE_LIMITS).ok


def test_too_many_buttons():
    buttons = [{"label": f"b{i}", "url": "https://a.example.com/x"} for i in range(26)]
    r = render_slack(card_of({"type": "Actions", "buttons": buttons}), limits=Limits(buttons=40))
    assert codes(r) == ["slack_too_many_buttons"]


def test_button_label_over_75_and_url_over_3000_are_refused():
    r = render_slack(
        card_of(
            {"type": "Actions", "buttons": [{"label": "b" * 80, "url": "https://a.example.com/x"}]}
        ),
        limits=Limits(button_label=100),
    )
    assert codes(r) == ["slack_text_too_long"]
    long_url = "https://a.example.com/" + "p" * 3000
    r = render_slack(
        card_of({"type": "Actions", "buttons": [{"label": "b", "url": long_url}]}),
        limits=Limits(url=5000),
    )
    assert codes(r) == ["slack_text_too_long"]


def test_alt_text_over_2000_is_refused():
    r = render_slack(
        card_of({"type": "Image", "url": "https://img.example.com/a.png", "alt": "a" * 2100}),
        limits=Limits(alt=3000, max_chars=9000),
        links=LinkPolicy(image_hosts=["img.example.com"]),
    )
    assert codes(r) == ["slack_text_too_long"]


def test_all_limit_problems_are_reported_together_with_paths():
    r = render_slack(
        card_of(
            {"type": "Text", "content": "x" * 3001},
            {"type": "Fields", "items": [{"label": "l", "value": "v"}] * 11},
        ),
        limits=Limits(text=5000, fields_items=50, max_chars=9000),
    )
    assert sorted(codes(r)) == ["slack_text_too_long", "slack_too_many_fields"]
    assert all(i.path.startswith("/elements/") for i in r.issues)


# ---- invalid cards and the link rule ---------------------------------------------------------


def test_an_invalid_card_returns_the_validation_issues_and_no_blocks():
    r = render_slack({"type": "Card", "v": 1, "title": "t", "children": [{"type": "Nope"}]})
    assert not r.ok and r.blocks == []
    assert "unknown_type" in codes(r)


def test_unreadable_input_is_an_issue_not_an_exception():
    r = render_slack("{not json")
    assert not r.ok and r.blocks == []


def test_render_respects_the_link_policy_for_buttons():
    r = render(
        {"type": "Actions", "buttons": [{"label": "x", "url": "https://a.example.com/x"}]},
        links=LinkPolicy(allowed_hosts=["only.example.com"]),
    )
    assert codes(r) == ["host_not_allowed"]


def _boom(host: str) -> bool:
    raise RuntimeError("secret detail that must not be echoed")


def test_a_link_policy_callable_that_raises_becomes_an_issue():
    button = {"type": "Actions", "buttons": [{"label": "x", "url": "https://a.example.com/x"}]}
    r = render(button, links=LinkPolicy(allowed_hosts=_boom))
    assert not r.ok and r.blocks == []
    assert codes(r) == ["link_policy_error"]
    assert "secret detail" not in r.issues[0].message
    r = render(IMG, links=LinkPolicy(image_hosts=_boom))
    assert codes(r) == ["link_policy_error"]


def test_validate_also_turns_a_raising_link_rule_into_an_issue():
    flat = parse(
        card_of({"type": "Actions", "buttons": [{"label": "x", "url": "https://a.b.co/"}]})
    )
    issues = validate(flat, links=LinkPolicy(allowed_hosts=_boom))
    assert [i.code for i in issues] == ["link_policy_error"]


def test_the_card_is_not_changed():
    c = card_of({"type": "Text", "content": "**x** <@U1>"})
    before = json.dumps(c, sort_keys=True)
    render_slack(c)
    assert json.dumps(c, sort_keys=True) == before


def test_mrkdwn_length_is_measured_after_escaping_but_plain_text_before():
    limits = Limits(text=5000, alt=3000, max_chars=9000, button_label=100)
    r = render_slack(card_of({"type": "Text", "content": "&" * 700}), limits=limits)
    assert codes(r) == ["slack_text_too_long"]  # 3500 once escaped
    btn = {"type": "Actions", "buttons": [{"label": "&" * 75, "url": "https://a.example.com/x"}]}
    assert render_slack(card_of(btn), limits=limits).ok
    alt = {"type": "Image", "url": "https://img.example.com/a.png", "alt": "<" * 2000}
    assert render_slack(
        card_of(alt), limits=limits, links=LinkPolicy(image_hosts=["img.example.com"])
    ).ok


def test_control_characters_are_still_refused():
    r = render(chart(title="a\u202eb"))
    assert not r.ok and r.blocks == []


def test_action_ids_stay_short_and_unique_for_a_very_long_element_key():
    from cardspec.slack import _Run

    props = {"buttons": [{"label": "b", "url": "https://a.example.com/x"}] * 2}
    ids: list[str] = []
    for key in ("k" * 400, "k" * 399 + "j", "k" * 400 + "~1"):
        run = _Run({"elements": {}}, Limits())
        run._actions(props, f"/elements/{key}/props")
        ids += [e["action_id"] for e in run.blocks[0]["elements"]]
    assert len(ids) == 6 and len(set(ids)) == 6
    assert all(len(i) <= 255 and i.startswith("cardspec-link-") for i in ids)
    # a short key keeps the readable form, and the id does not change between runs
    run = _Run({"elements": {}}, Limits())
    run._actions(props, "/elements/actions/props")
    assert run.blocks[0]["elements"][1]["action_id"] == "cardspec-link-actions-1"
