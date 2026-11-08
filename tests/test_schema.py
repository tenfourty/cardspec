from __future__ import annotations

import pytest

from cardspec import Limits, LinkPolicy
from cardspec.schema import ROLES, Bool, Ctx, Enum, List, Num, Obj, Opt, Str, Url, forbidden_char


def run(kind, value, mode="final", limits=None):
    ctx = Ctx(limits or Limits(), LinkPolicy(), mode)
    kind.check(value, "/p", ctx)
    return ctx


def codes_of(kind, value, **kw):
    return [i.code for i in run(kind, value, **kw).issues]


def test_every_role_is_usable():
    for role in ROLES:
        assert codes_of(Str(role), "x") == []


def test_str_max_may_be_a_limit_name_or_a_number():
    assert codes_of(Str("title", max="title"), "x" * 150) == []
    assert codes_of(Str("title", max="title"), "x" * 151) == ["too_long"]
    assert codes_of(Str("title", max=3), "xxxx") == ["too_long"]
    assert codes_of(Str("title", max="title"), "xx", limits=Limits(title=1)) == ["too_long"]


def test_str_counts_characters():
    ctx = run(Str("text"), "abc")
    assert ctx.chars == 3


def test_str_number_ok():
    assert codes_of(Str("value"), 5) == ["wrong_type"]
    assert codes_of(Str("value", number_ok=True), 5) == []
    assert codes_of(Str("value", number_ok=True), 10**20) == ["bad_number"]
    assert run(Str("value", number_ok=True), 1.5).chars == 3


def test_empty_rules():
    assert codes_of(Str("text"), "") == ["empty"]
    assert codes_of(Str("text", allow_empty=True), "") == []


def test_forbidden_char_helper():
    assert forbidden_char("plain") is None
    assert forbidden_char("a‮b") == "U+202E"
    assert forbidden_char("a\nb") == "U+000A"
    assert forbidden_char("a\nb", multiline=True) is None


def test_num_bool_enum():
    assert codes_of(Num(), 3) == [] and codes_of(Num(), 2.5) == []
    assert codes_of(Num(), True) == ["wrong_type"]
    assert codes_of(Num(), float("nan")) == ["bad_number"]
    assert codes_of(Num(positive=True), 0) == ["bad_number"]
    assert codes_of(Bool(), True) == [] and codes_of(Bool(), 1) == ["wrong_type"]
    assert codes_of(Enum("a", "b"), "a") == []
    assert codes_of(Enum("a", "b"), "c") == ["bad_value"]
    assert codes_of(Enum("a", "b"), ["a"]) == ["wrong_type"]
    with pytest.raises(ValueError):
        Enum()


def test_list_min_counts_only_when_final():
    kind = List(Str("text"), min=1)
    assert codes_of(kind, []) == ["too_few"]
    assert codes_of(kind, [], mode="open") == []


def test_list_over_max_does_not_check_every_item():
    kind = List(Str("text"), max=2)
    ctx = run(kind, [5] * 1000)
    assert [i.code for i in ctx.issues] == ["too_many"]


def test_obj_reports_unknown_and_missing():
    kind = Obj({"a": Str("text"), "b": Opt(Num())})
    assert codes_of(kind, {"a": "x"}) == []
    assert codes_of(kind, {"b": 1}) == ["missing_prop"]
    assert codes_of(kind, {"a": "x", "c": 1}) == ["unknown_key"]


def test_pointer_escaping_in_paths():
    ctx = run(Obj({"a": Str("text")}), {"a": "x", "a/b~c": 1})
    assert ctx.issues[0].path == "/p/a~1b~0c"


def test_url_kinds():
    assert codes_of(Url("link"), "https://example.com") == []
    assert codes_of(Url("link"), "http://example.com") == ["bad_url"]
    assert codes_of(Url("image"), "https://img.example.com/a.png") == ["image_host_not_allowed"]
    with pytest.raises(ValueError):
        Url("video")
