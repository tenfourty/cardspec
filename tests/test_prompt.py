from __future__ import annotations

import json
import re

from cardspec import STANDARD, Limits, LinkPolicy, catalogue_prompt, parse, validate

from .test_catalogue import kpi

POLICY = LinkPolicy(image_hosts={"img.example.com"})


def test_every_element_appears_in_the_prompt():
    text = catalogue_prompt(links=POLICY)
    for name in STANDARD.elements:
        assert re.search(rf"\b{name}\b", text), name


def test_every_example_in_the_prompt_is_json_that_validates():
    text = catalogue_prompt(links=POLICY)
    blocks = re.findall(r"```json\n(.*?)\n```", text, re.S)
    assert len(blocks) >= len(STANDARD.elements)
    for block in blocks:
        data = json.loads(block)
        if data.get("type") != "Card":
            data = {"type": "Card", "v": 1, "title": "Example", "children": [data]}
        assert validate(parse(data), links=POLICY) == [], block


def test_prompt_names_the_version_and_the_rules():
    text = catalogue_prompt(links=POLICY)
    assert '"v": 1' in text
    for rule in STANDARD.rules:
        assert rule in text


def test_prompt_states_the_limits_in_force():
    text = catalogue_prompt(limits=Limits(title=77, max_chars=1234))
    assert "77" in text and "1234" in text
    assert "150" in catalogue_prompt()


def test_prompt_follows_the_profile():
    assert "Image" not in catalogue_prompt(links=POLICY, profile="terminal")
    assert "Image" in catalogue_prompt(links=POLICY)
    assert "40000" in catalogue_prompt(profile="page")


def test_prompt_leaves_out_pictures_unless_hosts_are_listed():
    text = catalogue_prompt()
    assert "Image" not in text
    assert "no pictures" in text.lower()
    text = catalogue_prompt(links=POLICY)
    assert "img.example.com" in text


def test_prompt_is_deterministic_and_plain():
    assert catalogue_prompt() == catalogue_prompt()
    assert catalogue_prompt().isascii()


def test_extended_catalogue_prompt_includes_new_element():
    cat = STANDARD.extend(kpi(), allow_in=("Card",))
    text = catalogue_prompt(cat)
    assert "Kpi" in text and "One big number" in text
