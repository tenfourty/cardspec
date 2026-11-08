from __future__ import annotations

import pytest

from cardspec import STANDARD, Catalogue, Element, Limits, parse, validate
from cardspec.schema import Children, Enum, Opt, Str

from .conftest import codes, small_card


def kpi() -> Element:
    return Element(
        "Kpi",
        props={
            "name": Str("label", max=40),
            "value": Str("value", max=40, number_ok=True),
            "trend": Opt(Enum("up", "down")),
        },
        description="One big number with a name.",
        example={"type": "Kpi", "name": "Errors", "value": 0},
    )


def test_standard_catalogue_has_the_documented_elements():
    assert list(STANDARD.elements) == [
        "Card",
        "Section",
        "Text",
        "Fields",
        "Table",
        "Chart",
        "Divider",
        "Image",
        "Actions",
    ]
    assert STANDARD.root == "Card"
    assert STANDARD.versions == (1,)


def test_every_element_has_description_and_example():
    for el in STANDARD.elements.values():
        assert el.description.strip()
        assert el.example["type"] == el.name


def test_every_example_validates_inside_a_card():
    from cardspec import LinkPolicy

    policy = LinkPolicy(image_hosts={"img.example.com"})
    for el in STANDARD.elements.values():
        if el.name == "Card":
            raw = el.example
        else:
            raw = {"type": "Card", "v": 1, "title": "Example", "children": [el.example]}
        card = parse(raw)
        assert validate(card, links=policy) == [], el.name


def test_catalogue_is_immutable_data():
    with pytest.raises(TypeError):
        STANDARD.elements["X"] = kpi()  # type: ignore[index]


def test_extend_adds_a_working_element():
    cat = STANDARD.extend(kpi(), allow_in=("Card", "Section"))
    assert "Kpi" in cat.elements and "Kpi" not in STANDARD.elements
    raw = {
        "type": "Card",
        "v": 1,
        "title": "T",
        "children": [{"type": "Kpi", "name": "Errors", "value": 0, "trend": "down"}],
    }
    assert validate(parse(raw), catalogue=cat) == []
    assert codes(validate(parse(raw))) == ["unknown_type"]
    bad = {
        "type": "Card",
        "v": 1,
        "title": "T",
        "children": [{"type": "Kpi", "name": "E", "value": 0, "trend": "sideways"}],
    }
    assert codes(validate(parse(bad), catalogue=cat)) == ["bad_value"]


def test_extend_without_allow_in_is_not_a_child_of_anything():
    cat = STANDARD.extend(kpi())
    raw = {
        "type": "Card",
        "v": 1,
        "title": "T",
        "children": [{"type": "Kpi", "name": "E", "value": 0}],
    }
    assert "child_not_allowed" in codes(validate(parse(raw), catalogue=cat))


def test_extend_refuses_duplicates_and_unknown_parents():
    with pytest.raises(ValueError):
        STANDARD.extend(Element("Text", props={}, description="d", example={"type": "Text"}))
    with pytest.raises(ValueError):
        STANDARD.extend(kpi(), allow_in=("Nope",))


def test_element_names_are_checked():
    for bad in ("kpi", "Two Words", "A" * 21, ""):
        with pytest.raises(ValueError):
            Element(bad, props={}, description="d", example={"type": bad})


def test_children_must_name_known_elements():
    with pytest.raises(ValueError):
        Catalogue(
            elements=[
                Element(
                    "Card",
                    props={},
                    children=Children(("Ghost",)),
                    description="d",
                    example={"type": "Card"},
                )
            ],
            root="Card",
            versions=(1,),
            rules=(),
            profiles={},
        )


def test_string_kinds_must_name_a_role():
    with pytest.raises(TypeError):
        Str()  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        Str("not-a-role")
    with pytest.raises(ValueError):
        Str("")


def test_limit_names_are_checked_when_the_catalogue_is_built():
    with pytest.raises(ValueError):
        Element(
            "Foo",
            props={"a": Str("text", max="no_such_limit")},
            description="d",
            example={"type": "Foo"},
        ).check_limits(Limits())


# ---- profiles -----------------------------------------------------------------------


def test_standard_profiles():
    assert set(STANDARD.profiles) >= {"slack", "page", "terminal"}
    slack = STANDARD.profile("slack")
    assert slack.limits == Limits()
    assert slack.elements is None
    page = STANDARD.profile("page")
    assert page.limits.table_rows == 500 and page.limits.max_chars == 40000
    assert page.limits.max_per_type.get("Table", 99) > 1
    assert "Image" not in STANDARD.profile("terminal").elements  # type: ignore[operator]


def test_unknown_profile():
    with pytest.raises(KeyError):
        STANDARD.profile("fax")
    with pytest.raises(KeyError):
        validate(small_card(), profile="fax")


def test_profile_rejects_what_the_surface_cannot_show():
    card = parse(
        {
            "type": "Card",
            "v": 1,
            "title": "T",
            "children": [{"type": "Image", "url": "https://img.example.com/a.png", "alt": "a"}],
        }
    )
    from cardspec import LinkPolicy

    policy = LinkPolicy(image_hosts={"img.example.com"})
    assert validate(card, links=policy) == []
    issues = validate(card, links=policy, profile="terminal")
    assert codes(issues) == ["element_not_in_profile"]
    assert issues[0].path == "/elements/image/type"


def test_profile_supplies_limits_unless_given():
    rows = [["a", "b"]] * 60
    card = parse(
        {
            "type": "Card",
            "v": 1,
            "title": "T",
            "children": [{"type": "Table", "headers": ["a", "b"], "rows": rows}],
        }
    )
    assert "too_many" in codes(validate(card, limits=Limits(max_chars=10**6)))
    assert validate(card, profile="page") == []
    # explicit limits win over the profile's
    assert "too_many" in codes(validate(card, profile="page", limits=Limits(max_chars=10**6)))


def test_profile_elements_must_exist_in_the_catalogue():
    with pytest.raises(ValueError):
        Catalogue(
            elements=list(STANDARD.elements.values()),
            root="Card",
            versions=(1,),
            rules=(),
            profiles={"x": {"elements": ["Ghost"]}},
        )
