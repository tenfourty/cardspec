from __future__ import annotations

import json
import math

import pytest

from cardspec import CardError, Limits, parse, validate

from .conftest import NESTED_EXAMPLE, small_card


def parse_codes(raw, **kw):
    with pytest.raises(CardError) as info:
        parse(raw, **kw)
    return [i.code for i in info.value.issues]


def test_nested_form_becomes_flat_form_and_is_valid():
    card = parse(json.dumps(NESTED_EXAMPLE))
    assert card["v"] == 1
    assert card["root"] == "card"
    assert set(card) == {"v", "root", "elements"}
    els = card["elements"]
    assert els["card"]["type"] == "Card"
    assert els["card"]["props"] == {
        "title": "Deploy: web 2026.11.8",
        "subtitle": "Finished 14:02, 3 minutes",
    }
    assert [els[k]["type"] for k in els["card"]["children"]] == [
        "Text",
        "Fields",
        "Table",
        "Chart",
        "Divider",
        "Actions",
    ]
    assert els["card"]["children"] == ["text", "fields", "table", "chart", "divider", "actions"]
    assert els["divider"] == {"type": "Divider", "props": {}}
    assert validate(card) == []


def test_repeated_types_get_distinct_keys():
    raw = {
        "type": "Card",
        "v": 1,
        "title": "T",
        "children": [{"type": "Text", "content": "a"}, {"type": "Text", "content": "b"}],
    }
    card = parse(raw)
    assert card["elements"]["card"]["children"] == ["text", "text-2"]
    assert card["elements"]["text-2"]["props"] == {"content": "b"}


def test_nested_section_children_are_converted():
    raw = {
        "type": "Card",
        "v": 1,
        "title": "T",
        "children": [
            {"type": "Section", "title": "S", "children": [{"type": "Text", "content": "x"}]}
        ],
    }
    card = parse(raw)
    assert card["elements"]["section"]["children"] == ["text"]
    assert validate(card) == []


def test_flat_form_passes_through_unchanged():
    assert parse(json.dumps(small_card())) == small_card()


def test_accepts_bytes_and_dict():
    assert parse(json.dumps(small_card()).encode()) == small_card()
    assert parse(small_card()) == small_card()


def test_parse_does_not_change_the_input_dict():
    raw = json.loads(json.dumps(NESTED_EXAMPLE))
    parse(raw)
    assert raw == NESTED_EXAMPLE


def test_too_large_is_refused_before_parsing():
    assert parse_codes("x" * 100, limits=Limits(max_bytes=50)) == ["too_large"]
    assert parse_codes(b"x" * 100, limits=Limits(max_bytes=50)) == ["too_large"]


def test_size_counts_bytes_not_characters():
    raw = json.dumps({"a": "é" * 30}, ensure_ascii=False)
    assert parse_codes(raw, limits=Limits(max_bytes=50)) == ["too_large"]


def test_dict_input_size_is_checked_too():
    big = small_card()
    big["elements"]["note"]["props"]["content"] = "y" * 500
    assert parse_codes(big, limits=Limits(max_bytes=200)) == ["too_large"]


def test_deep_nesting_stops_early_and_does_not_crash():
    assert parse_codes("[" * 30000) == ["json_too_deep"]
    deep = "[" * 40 + "]" * 40
    assert parse_codes(deep, limits=Limits(max_json_depth=10)) == ["json_too_deep"]


def test_deep_dict_input_is_refused():
    node: list = []
    for _ in range(50):
        node = [node]
    assert parse_codes({"type": "Card", "v": 1, "title": "x", "children": node}) == [
        "json_too_deep"
    ]


def test_brackets_inside_strings_do_not_count_as_depth():
    raw = json.dumps({"a": "[" * 500})
    # parses as JSON; fails later as an unknown form, not as too deep
    assert "json_too_deep" not in parse_codes(raw)


def test_duplicate_keys_refused():
    assert parse_codes('{"v": 1, "v": 2}') == ["duplicate_key"]


@pytest.mark.parametrize("text", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_numbers_refused(text):
    assert parse_codes(f'{{"a": {text}}}') == ["bad_number"]


def test_non_finite_float_in_dict_refused():
    assert parse_codes({"type": "Card", "v": 1, "title": math.nan}) == ["bad_number"]


def test_bad_json_and_bad_encoding():
    assert parse_codes("{nope") == ["bad_json"]
    assert parse_codes(b"\xff\xfe\x00") == ["bad_encoding"]


def test_non_json_values_in_dict_refused():
    assert parse_codes({"type": "Card", "v": 1, "title": {1, 2}}) == ["wrong_type"]
    assert parse_codes({"type": "Card", "v": 1, "title": "x", 5: "y"}) == ["wrong_type"]


@pytest.mark.parametrize("raw", ["[]", '"text"', "7", "null"])
def test_top_level_must_be_an_object(raw):
    assert parse_codes(raw) == ["not_object"]


def test_unknown_form_refused():
    assert parse_codes('{"hello": 1}') == ["unknown_form"]


def test_sugar_children_must_be_a_list_of_objects():
    assert parse_codes({"type": "Card", "v": 1, "title": "x", "children": "no"}) == ["wrong_type"]
    assert parse_codes({"type": "Card", "v": 1, "title": "x", "children": ["no"]}) == ["wrong_type"]


def test_sugar_element_needs_a_type_string():
    assert parse_codes({"type": "Card", "v": 1, "title": "x", "children": [{"content": "a"}]}) == [
        "missing_type"
    ]


def test_sugar_element_count_is_capped_while_converting():
    raw = {
        "type": "Card",
        "v": 1,
        "title": "x",
        "children": [{"type": "Divider"} for _ in range(10)],
    }
    assert parse_codes(raw, limits=Limits(max_elements=5)) == ["too_many_elements"]


def test_issue_paths_point_into_the_input():
    with pytest.raises(CardError) as info:
        parse({"type": "Card", "v": 1, "title": "x", "children": [{"type": "Text"}, 3]})
    issue = info.value.issues[0]
    assert issue.path == "/children/1"


def test_card_error_message_lists_issues():
    with pytest.raises(CardError) as info:
        parse("[]")
    assert "not_object" in str(info.value)
