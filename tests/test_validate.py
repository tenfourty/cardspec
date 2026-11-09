from __future__ import annotations

import copy
import json

import pytest

from cardspec import Issue, Limits, LinkPolicy, parse, validate

from .conftest import NESTED_EXAMPLE, codes, small_card


def wrap(*children, **card_props):
    """A flat card whose root holds the given (key, type, props) children in order."""
    els = {"card": {"type": "Card", "props": {"title": "T", **card_props}, "children": []}}
    for key, typ, props in children:
        els["card"]["children"].append(key)
        els[key] = {"type": typ, "props": props}
    return {"v": 1, "root": "card", "elements": els}


def text(content="hello"):
    return ("text", "Text", {"content": content})


def table(headers=("a", "b"), rows=(("1", "2"),), **extra):
    return ("table", "Table", {"headers": list(headers), "rows": [list(r) for r in rows], **extra})


def chart(**props):
    base = {
        "title": "C",
        "kind": "bar",
        "categories": ["x", "y"],
        "series": [{"name": "s", "values": [1, 2]}],
    }
    base.update(props)
    return ("chart", "Chart", base)


def only(issues, code):
    found = [i for i in issues if i.code == code]
    assert found, f"no {code} in {[(i.code, i.path) for i in issues]}"
    return found[0]


def test_minimal_card_is_valid(card):
    assert validate(card) == []


def test_worked_example_is_valid():
    assert validate(parse(NESTED_EXAMPLE)) == []


def test_issue_is_plain_data():
    issue = Issue(path="/a", code="too_long", message="m", limit=3, actual=4)
    assert issue.to_dict() == {
        "path": "/a",
        "code": "too_long",
        "message": "m",
        "limit": 3,
        "actual": 4,
    }
    assert Issue("/a", "c", "m").to_dict() == {"path": "/a", "code": "c", "message": "m"}


# ---- the document -------------------------------------------------------------------


@pytest.mark.parametrize("bad", [[], "x", 1, None])
def test_document_must_be_an_object(bad):
    assert codes(validate(bad)) == ["not_object"]


def test_unknown_top_level_key(card):
    card["extra"] = 1
    assert only(validate(card), "unknown_key").path == "/extra"


def test_version_required_integer_and_known(card):
    del card["v"]
    assert codes(validate(card)) == ["missing_version"]
    card["v"] = "1"
    assert codes(validate(card)) == ["wrong_type"]
    card["v"] = True
    assert codes(validate(card)) == ["wrong_type"]
    card["v"] = 2
    issue = only(validate(card), "unsupported_version")
    assert "1" in issue.message
    assert issue.path == "/v"


def test_root_and_elements_required(card):
    del card["root"]
    assert "missing_root" in codes(validate(card))
    card["root"] = "nothere"
    assert only(validate(card), "missing_root").path == "/root"
    card["root"] = "Not A Key"
    assert "bad_key" in codes(validate(card))
    del card["elements"]
    assert "missing_elements" in codes(validate(card))


def test_elements_must_be_object_of_objects(card):
    card["elements"]["note"] = "x"
    assert only(validate(card), "wrong_type").path == "/elements/note"


@pytest.mark.parametrize("key", ["A", "1a", "a_b", "a" * 33, "", "a b"])
def test_bad_element_keys(card, key):
    card["elements"][key] = {"type": "Divider", "props": {}}
    assert "bad_key" in codes(validate(card))


def test_key_at_the_length_limit_is_fine(card):
    key = "a" * 32
    card["elements"][key] = {"type": "Divider", "props": {}}
    card["elements"]["card"]["children"].append(key)
    assert validate(card) == []


def test_root_must_be_a_card(card):
    card["elements"]["note"]["children"] = []
    card["root"] = "note"
    card["elements"]["card"]["children"] = []
    issues = validate(card)
    assert only(issues, "root_not_card").path == "/elements/note"


def test_unknown_type(card):
    card["elements"]["note"]["type"] = "Blink"
    issue = only(validate(card), "unknown_type")
    assert issue.path == "/elements/note/type"
    assert "Text" in issue.message


def test_element_shape(card):
    card["elements"]["note"]["style"] = "x"
    assert only(validate(card), "unknown_key").path == "/elements/note/style"
    del card["elements"]["note"]["style"]
    del card["elements"]["note"]["type"]
    assert only(validate(card), "missing_type").path == "/elements/note"


def test_props_default_to_empty(card):
    card["elements"]["sep"] = {"type": "Divider"}
    card["elements"]["card"]["children"].append("sep")
    assert validate(card) == []


# ---- props --------------------------------------------------------------------------


def test_missing_required_prop(card):
    del card["elements"]["note"]["props"]["content"]
    issue = only(validate(card), "missing_prop")
    assert issue.path == "/elements/note/props/content"


def test_unknown_prop_is_an_issue_not_dropped(card):
    card["elements"]["note"]["props"]["colour"] = "red"
    assert only(validate(card), "unknown_key").path == "/elements/note/props/colour"


def test_wrong_types(card):
    card["elements"]["note"]["props"]["content"] = ["x"]
    assert only(validate(card), "wrong_type").path == "/elements/note/props/content"
    card["elements"]["note"]["props"] = []
    assert only(validate(card), "wrong_type").path == "/elements/note/props"


def test_empty_string_refused_where_required(card):
    card["elements"]["card"]["props"]["title"] = "   "
    assert only(validate(card), "empty").path == "/elements/card/props/title"


def test_enum_value(card):
    card["elements"]["note"]["props"]["style"] = "loud"
    issue = only(validate(card), "bad_value")
    assert "muted" in issue.message
    card["elements"]["note"]["props"]["style"] = "muted"
    assert validate(card) == []


def test_numbers_are_allowed_as_display_values():
    card = wrap(
        ("kpi", "Fields", {"items": [{"label": "n", "value": 0}, {"label": "f", "value": 1.5}]})
    )
    assert validate(card) == []


def test_bool_is_not_a_number():
    card = wrap(("kpi", "Fields", {"items": [{"label": "n", "value": True}]}))
    assert only(validate(card), "wrong_type").path == "/elements/kpi/props/items/0/value"


def test_non_finite_display_number_refused():
    card = wrap(("kpi", "Fields", {"items": [{"label": "n", "value": float("inf")}]}))
    assert "bad_number" in codes(validate(card))


@pytest.mark.parametrize(
    "char",
    [
        "\x00",
        "\x07",
        "\x1b",
        "\r",
        "\t",
        "‮",
        "‪",
        "⁦",
        "​",
        "‍",
        "﻿",
        "⁠",
        "­",
        " ",
        " ",
        "\x7f",
        "ㅤ",
        "\ud800",
    ],
)
def test_forbidden_characters_refused_everywhere(char):
    card = wrap(text("a" + char + "b"))
    assert only(validate(card), "forbidden_char").path == "/elements/text/props/content"
    card = wrap(("kpi", "Fields", {"items": [{"label": "a" + char, "value": "v"}]}))
    assert "forbidden_char" in codes(validate(card))
    assert "forbidden_char" in codes(validate(wrap(text(), title="x" + char)))


def test_newline_only_in_text_content():
    assert validate(wrap(text("line one\nline two"))) == []
    assert "forbidden_char" in codes(validate(wrap(text(), title="a\nb")))
    assert "forbidden_char" in codes(validate(wrap(table(rows=[["a\nb", "c"]]))))


def test_ordinary_unicode_is_fine():
    assert validate(wrap(text("café — 日本語 \U0001f600"))) == []


# ---- limits: at the limit passes, one over is refused, with limit and actual --------


def over(card, code, limit):
    issue = only(validate(card), code)
    assert issue.limit == limit and issue.actual is not None and issue.actual > limit
    return issue


@pytest.mark.parametrize(
    ("build", "n", "path"),
    [
        (lambda s: wrap(text(), title=s), 150, "/elements/card/props/title"),
        (lambda s: wrap(text(), subtitle=s), 300, "/elements/card/props/subtitle"),
        (lambda s: wrap(text(s)), 2000, "/elements/text/props/content"),
        (
            lambda s: wrap(("kpi", "Fields", {"items": [{"label": s, "value": "v"}]})),
            60,
            "/elements/kpi/props/items/0/label",
        ),
        (
            lambda s: wrap(("kpi", "Fields", {"items": [{"label": "l", "value": s}]})),
            200,
            "/elements/kpi/props/items/0/value",
        ),
        (lambda s: wrap(table(rows=[[s, "x"]])), 200, "/elements/table/props/rows/0/0"),
        (
            lambda s: wrap(
                ("a", "Actions", {"buttons": [{"label": s, "url": "https://example.com"}]})
            ),
            40,
            "/elements/a/props/buttons/0/label",
        ),
        (lambda s: wrap(chart(categories=[s, "y"])), 24, "/elements/chart/props/categories/0"),
    ],
)
def test_string_limits(build, n, path):
    huge = Limits(max_chars=10**6)
    assert validate(build("x" * n), limits=huge) == []
    issues = validate(build("x" * (n + 1)), limits=huge)
    found = only(issues, "too_long")
    assert found.path == path
    assert found.limit == n and found.actual == n + 1


def test_limit_counts_characters_not_bytes():
    assert validate(wrap(text(), title="é" * 150)) == []


def test_fields_count():
    items = lambda n: [{"label": f"l{i}", "value": "v"} for i in range(n)]  # noqa: E731
    assert validate(wrap(("k", "Fields", {"items": items(10)}))) == []
    over(wrap(("k", "Fields", {"items": items(11)})), "too_many", 10)
    assert "too_few" in codes(validate(wrap(("k", "Fields", {"items": []}))))


def test_table_limits():
    assert (
        validate(wrap(table(headers=[str(i) for i in range(8)], rows=[[str(i) for i in range(8)]])))
        == []
    )
    wide = wrap(table(headers=[str(i) for i in range(9)], rows=[[str(i) for i in range(9)]]))
    assert only(validate(wide), "too_many").limit == 8
    rows = lambda n: [["a", "b"] for _ in range(n)]  # noqa: E731
    assert validate(wrap(table(rows=rows(50))), limits=Limits(max_chars=10**6)) == []
    over(wrap(table(rows=rows(51))), "too_many", 50)


def test_table_row_width():
    issue = only(validate(wrap(table(rows=[["1", "2"], ["1"]]))), "row_width")
    assert issue.path == "/elements/table/props/rows/1"
    assert "1 cell" in issue.message and "2 headers" in issue.message


def test_table_align_width_and_values():
    assert validate(wrap(table(align=["left", "right"]))) == []
    assert only(validate(wrap(table(align=["left"]))), "align_width").path.endswith("/align")
    assert "bad_value" in codes(validate(wrap(table(align=["left", "up"]))))


def test_table_without_rows_is_allowed_for_streaming():
    assert validate(wrap(table(rows=[]))) == []


def test_only_one_table_per_card():
    card = wrap(table(), ("table-2", "Table", {"headers": ["a"], "rows": []}))
    issue = only(validate(card), "too_many_of_type")
    assert issue.limit == 1 and issue.actual == 2 and "Table" in issue.message
    assert validate(card, limits=Limits(max_per_type={"Table": 2})) == []


def test_chart_limits():
    cats = lambda n: [str(i) for i in range(n)]  # noqa: E731
    ok = chart(categories=cats(12), series=[{"name": "s", "values": [1] * 12}])
    assert validate(wrap(ok)) == []
    bad = chart(categories=cats(13), series=[{"name": "s", "values": [1] * 13}])
    assert only(validate(wrap(bad)), "too_many").limit == 12
    series = lambda n: [{"name": f"s{i}", "values": [1, 2]} for i in range(n)]  # noqa: E731
    assert validate(wrap(chart(series=series(3)))) == []
    assert only(validate(wrap(chart(series=series(4)))), "too_many").limit == 3


def test_chart_shapes():
    for kind in ("line", "area", "bar"):
        assert validate(wrap(chart(kind=kind))) == []
    pie = (
        "chart",
        "Chart",
        {
            "title": "P",
            "kind": "pie",
            "segments": [{"label": "a", "value": 1}, {"label": "b", "value": 2.5}],
        },
    )
    assert validate(wrap(pie)) == []
    assert "bad_value" in codes(validate(wrap(chart(kind="radar"))))


def test_chart_series_length_must_match_categories():
    issue = only(validate(wrap(chart(series=[{"name": "s", "values": [1]}]))), "series_length")
    assert issue.path == "/elements/chart/props/series/0/values"
    assert "2 categories" in issue.message


def test_chart_wrong_props_for_kind():
    no_series = ("chart", "Chart", {"title": "C", "kind": "bar", "categories": ["a"]})
    assert only(validate(wrap(no_series)), "chart_shape")
    pie_with_series = (
        "chart",
        "Chart",
        {"title": "C", "kind": "pie", "segments": [{"label": "a", "value": 1}], "series": []},
    )
    assert only(validate(wrap(pie_with_series)), "chart_shape")
    pie_empty = ("chart", "Chart", {"title": "C", "kind": "pie"})
    assert only(validate(wrap(pie_empty)), "chart_shape")


def test_chart_numbers_must_be_finite_and_pie_values_positive():
    nan = chart(series=[{"name": "s", "values": [1, float("nan")]}])
    assert "bad_number" in codes(validate(wrap(nan)))
    pie = (
        "chart",
        "Chart",
        {"title": "P", "kind": "pie", "segments": [{"label": "a", "value": 0}]},
    )
    issue = only(validate(wrap(pie)), "bad_number")
    assert "greater than zero" in issue.message
    neg = chart(series=[{"name": "s", "values": [-3, 2]}])
    assert validate(wrap(neg)) == []  # a bar or line may go negative


def test_chart_values_are_numbers_not_strings():
    bad = chart(series=[{"name": "s", "values": ["1", 2]}])
    assert "wrong_type" in codes(validate(wrap(bad)))


def test_buttons():
    btn = lambda n: [{"label": f"b{i}", "url": "https://example.com"} for i in range(n)]  # noqa: E731
    assert validate(wrap(("a", "Actions", {"buttons": btn(5)}))) == []
    over(wrap(("a", "Actions", {"buttons": btn(6)})), "too_many", 5)


def test_button_urls_use_the_link_policy():
    card = wrap(("a", "Actions", {"buttons": [{"label": "x", "url": "http://example.com"}]}))
    issue = only(validate(card), "bad_url")
    assert issue.path == "/elements/a/props/buttons/0/url"
    ok = wrap(("a", "Actions", {"buttons": [{"label": "x", "url": "https://example.com/p"}]}))
    assert validate(ok) == []
    assert codes(validate(ok, links=LinkPolicy(allowed_hosts={"dash.example.com"}))) == [
        "host_not_allowed"
    ]


def test_button_url_length_limit():
    url = "https://example.com/" + "a" * 1980
    card = wrap(("a", "Actions", {"buttons": [{"label": "x", "url": url}]}))
    assert validate(card) == []
    card = wrap(("a", "Actions", {"buttons": [{"label": "x", "url": url + "a"}]}))
    assert only(validate(card), "too_long").limit == 2000


def test_no_pictures_unless_hosts_are_listed():
    card = wrap(("img", "Image", {"url": "https://img.example.com/a.png", "alt": "A chart"}))
    assert codes(validate(card)) == ["image_host_not_allowed"]
    policy = LinkPolicy(image_hosts={"img.example.com"})
    assert validate(card, links=policy) == []
    card["elements"]["img"]["props"]["url"] = "http://img.example.com/a.png"
    assert codes(validate(card, links=policy)) == ["bad_url"]


def test_image_needs_alt_text():
    card = wrap(("img", "Image", {"url": "https://img.example.com/a.png"}))
    issues = validate(card, links=LinkPolicy(image_hosts={"img.example.com"}))
    assert only(issues, "missing_prop").path == "/elements/img/props/alt"


# ---- structure ----------------------------------------------------------------------


def test_missing_child_allowed_while_open_but_not_final(card):
    card["elements"]["card"]["children"].append("later")
    issue = only(validate(card), "missing_child")
    assert issue.path == "/elements/card/children/1"
    assert validate(card, mode="open") == []


def test_orphan_allowed_while_open_but_not_final(card):
    card["elements"]["spare"] = {"type": "Divider", "props": {}}
    assert only(validate(card), "orphaned_element").path == "/elements/spare"
    assert validate(card, mode="open") == []


def test_orphan_content_is_still_checked_in_every_mode(card):
    card["elements"]["spare"] = {"type": "Text", "props": {"content": "x‮"}}
    assert "forbidden_char" in codes(validate(card, mode="open"))


def test_orphan_counts_toward_element_and_character_budgets():
    card = wrap(text())
    for i in range(40):
        card["elements"][f"o{i}"] = {"type": "Divider", "props": {}}
    assert "too_many_elements" in codes(validate(card, mode="open"))
    card = wrap(text())
    card["elements"]["spare"] = {"type": "Text", "props": {"content": "x" * 2000}}
    card["elements"]["spare2"] = {"type": "Text", "props": {"content": "x" * 2000}}
    assert "too_many_chars" in codes(validate(card, mode="open"))


def test_element_count_limit():
    card = wrap(*[(f"d{i}", "Divider", {}) for i in range(39)])
    assert len(card["elements"]) == 40
    assert validate(card) == []
    card = wrap(*[(f"d{i}", "Divider", {}) for i in range(40)])
    issue = only(validate(card), "too_many_elements")
    assert issue.limit == 40 and issue.actual == 41


def test_huge_card_is_refused_without_walking_it():
    card = wrap(text())
    for i in range(5000):
        card["elements"][f"d{i}"] = {"type": "Text", "props": {"content": "‮"}}
    assert codes(validate(card)) == ["too_many_elements"]


def test_cycle():
    card = {
        "v": 1,
        "root": "card",
        "elements": {
            "card": {"type": "Card", "props": {"title": "T"}, "children": ["sec"]},
            "sec": {"type": "Section", "props": {}, "children": ["sec"]},
        },
    }
    assert "cycle" in codes(validate(card))
    card["elements"]["sec"]["children"] = ["card"]
    assert "cycle" in codes(validate(card))


def test_duplicate_child_and_shared_child(card):
    card["elements"]["card"]["children"] = ["note", "note"]
    assert only(validate(card), "duplicate_child").path == "/elements/card/children/1"
    card["elements"]["card"]["children"] = ["note", "sec"]
    card["elements"]["sec"] = {"type": "Section", "props": {}, "children": ["note"]}
    assert "duplicate_child" in codes(validate(card))


def test_child_not_allowed(card):
    # a Card inside a Card, a Section inside a Section, children under a leaf
    card["elements"]["inner"] = {"type": "Card", "props": {"title": "x"}, "children": []}
    card["elements"]["card"]["children"].append("inner")
    assert only(validate(card), "child_not_allowed").path == "/elements/card/children/1"
    card = small_card()
    card["elements"]["s1"] = {"type": "Section", "props": {}, "children": ["s2"]}
    card["elements"]["s2"] = {"type": "Section", "props": {}, "children": []}
    card["elements"]["card"]["children"].append("s1")
    assert only(validate(card), "child_not_allowed").path == "/elements/s1/children/0"
    card = small_card()
    card["elements"]["note"]["children"] = ["card"]
    assert "child_not_allowed" in codes(validate(card))


def test_children_must_be_a_list_of_strings(card):
    card["elements"]["card"]["children"] = "note"
    assert only(validate(card), "wrong_type").path == "/elements/card/children"
    card["elements"]["card"]["children"] = [3]
    assert only(validate(card), "wrong_type").path == "/elements/card/children/0"


def test_nesting_depth():
    sec = {"type": "Section", "props": {}, "children": ["note"]}
    card = small_card()
    card["elements"]["sec"] = sec
    card["elements"]["card"]["children"] = ["sec"]
    assert validate(card) == []  # Card, Section, Text = 3 deep
    assert only(validate(card, limits=Limits(max_nesting=2)), "too_deep").limit == 2


def test_total_characters_limit():
    card = wrap(("t1", "Text", {"content": "x" * 2000}), ("t2", "Text", {"content": "y" * 1994}))
    assert validate(card, limits=Limits(max_chars=3995)) == []
    issue = only(validate(card, limits=Limits(max_chars=3994)), "too_many_chars")
    assert issue.limit == 3994 and issue.actual == 3995


def test_urls_are_not_counted_as_text():
    url = "https://example.com/" + "a" * 1900
    buttons = [{"label": "b", "url": url}] * 3
    card = wrap(("a", "Actions", {"buttons": buttons}), title="T")
    assert validate(card, limits=Limits(max_chars=10)) == []


def test_numbers_count_by_their_text_length():
    card = wrap(("k", "Fields", {"items": [{"label": "l", "value": 12345}]}), title="T")
    # T + l + 12345
    assert validate(card, limits=Limits(max_chars=7)) == []
    assert "too_many_chars" in codes(validate(card, limits=Limits(max_chars=6)))


def test_reports_everything_up_to_fifty():
    card = wrap(*[(f"t{i}", "Text", {"content": 5}) for i in range(39)])
    issues = validate(card)
    assert len(issues) == 39
    card = wrap(*[(f"t{i}", "Text", {"content": [], "style": "x", "more": 1}) for i in range(39)])
    assert len(validate(card)) == 50


def test_validate_never_raises_on_hostile_input():
    hostile = [
        None,
        5,
        "x",
        [],
        {},
        {"v": 1},
        {"v": 1, "root": 5, "elements": 5},
        {"v": 1, "root": "a", "elements": {"a": None}},
        {"v": 1, "root": "a", "elements": {"a": {"type": 5}}},
        {"v": 1, "root": "a", "elements": {"a": {"type": "Card", "props": None, "children": None}}},
        {
            "v": 1,
            "root": "a",
            "elements": {"a": {"type": "Card", "props": {"title": {}}, "children": [[]]}},
        },
        {"v": [], "root": [], "elements": []},
    ]
    for item in hostile:
        for mode in ("final", "open"):
            result = validate(item, mode=mode)
            assert all(isinstance(i, Issue) for i in result)
            json.dumps([i.to_dict() for i in result])


def test_validate_does_not_change_its_input(card):
    before = copy.deepcopy(card)
    validate(card)
    validate(card, mode="open")
    assert card == before


def test_mode_must_be_known(card):
    with pytest.raises(ValueError):
        validate(card, mode="loose")


# ---- limits value and profiles ------------------------------------------------------


def test_limits_are_frozen_and_checked():
    limits = Limits()
    with pytest.raises(AttributeError):
        limits.title = 1  # type: ignore[misc]
    with pytest.raises(ValueError):
        Limits(title=0)
    assert limits.replace(title=10).title == 10


def test_default_limits_match_the_format():
    d = Limits()
    assert (d.max_bytes, d.max_chars, d.max_elements) == (32 * 1024, 4000, 40)
    assert (d.title, d.subtitle, d.text) == (150, 300, 2000)
    assert (d.fields_items, d.field_label, d.field_value) == (10, 60, 200)
    assert (d.table_rows, d.table_cols, d.cell) == (50, 8, 200)
    assert (d.chart_categories, d.chart_series, d.chart_label) == (12, 3, 24)
    assert (d.buttons, d.button_label, d.url, d.image_url, d.alt) == (5, 40, 2000, 1000, 200)
    assert d.max_nesting == 3
    assert d.max_per_type == {"Table": 1}


def test_validate_does_not_raise_on_a_dict_that_json_could_not_hold():
    # validate takes any Python value, not only parsed cards; it must report, never raise.
    body = {"type": "Card", "props": {"title": "t"}, "children": []}
    codes = [i.code for i in validate({"v": 1, "root": "card", "elements": {1: body}})]
    assert "bad_key" in codes
    codes = [i.code for i in validate({"v": 10**5000, "root": "card", "elements": {"card": body}})]
    assert "unsupported_version" in codes
