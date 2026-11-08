# cardspec

Describe a small card (a title, some text, a few numbers, a table, a chart, some buttons) as
data. Check it. Hand the model that writes it the exact instructions for it. Standard library
only, Python 3.11 or later.

cardspec is **inspired by and derived from [json-render](https://github.com/vercel-labs/json-render)**
(Apache-2.0, Copyright 2025 Vercel Inc.): the catalogue of typed elements, the flat
"root plus elements" spec, validation that returns path-addressed issues, and prompts
generated from the catalogue are its ideas, rewritten in Python. The code is new. See
[NOTICE](NOTICE) for what was kept and what changed. cardspec is licensed under the Apache
License 2.0 ([LICENSE](LICENSE)).

This release is slice 1: the schema kit, the catalogue, the `standard` catalogue, `parse`,
`validate` and the model prompt. Walking and rewriting strings, patches, and the renderers
(text, Slack, HTML) come in later releases.

## A card

A card is a tree of elements. Write it in one go in the *nested form*:

```json
{
  "type": "Card", "v": 1,
  "title": "Deploy: web 2026.11.8",
  "children": [
    {"type": "Text", "content": "**Healthy.** All checks passed."},
    {"type": "Fields", "items": [{"label": "Errors (1h)", "value": 0}]},
    {"type": "Table", "headers": ["Step", "Result"], "rows": [["build", "ok"]]},
    {"type": "Actions", "buttons": [{"label": "Open", "url": "https://dash.example.com/web"}]}
  ]
}
```

`parse` turns that into the *flat form*, which is what is stored, checked and (later) patched:
`{"v": 1, "root": "card", "elements": {"<key>": {"type", "props", "children"}}}`. A flat card
is accepted as it is.

```python
from cardspec import parse, validate, catalogue_prompt, Limits, LinkPolicy, CardError

card = parse(raw_text)  # raises CardError(issues) if it cannot be read
issues = validate(card)  # [] means valid; each Issue has path, code, message
for issue in issues:
    print(issue.to_dict())  # send these back to the model that wrote the card

text_for_the_model = catalogue_prompt()  # generated from the same data that validates
```

## What it checks

* The shape: unknown types, unknown keys and wrong kinds of value are issues, never ignored.
* Sizes: every limit lives in `Limits` and a card over a limit is refused, never cut short.
* Characters: control, invisible and text-direction characters are refused anywhere in a card.
* Structure: missing children, orphans, cycles, shared children, too-deep nesting.
* Links: `LinkPolicy` allows https only, no user names, no IP addresses or `localhost`, no
  punycode, and optionally only hosts you list. Pictures are allowed **only** from hosts you list
  in `LinkPolicy(image_hosts=...)`; with none listed, a card cannot hold a picture.
* Surfaces: `validate(card, profile="terminal")` rejects what that surface cannot show, and
  takes that surface's limits.

`validate(card, mode="open")` is for a card still being built: a child may name an element that
has not arrived yet. The default `mode="final"` is for a finished card.

## Rule for renderers: card text is plain text

`validate` accepts `&`, `<` and `>` in text, because they are ordinary characters. Some surfaces
give them meaning (in Slack, `<https://x|y>` is a hidden link and `<@U123>` or `<!here>` is a
mention). So **every renderer must escape `&`, `<` and `>` in every text value** (use
`cardspec.escape_mrkdwn` for Slack) so that card text can never form a link or a mention. Links
come only from link elements that `LinkPolicy` has checked, never from text.

## Your own catalogue

A catalogue is data, so you can extend the standard one:

```python
from cardspec import STANDARD, Element
from cardspec.schema import Str, Opt, Enum

kpi = Element(
    "Kpi",
    props={"name": Str("label", max=40), "value": Str("value", max=40, number_ok=True)},
    description="One big number with a name.",
    example={"type": "Kpi", "name": "Errors", "value": 0},
)
mine = STANDARD.extend(kpi, allow_in=("Card", "Section"))
```

Every text prop must name a role (`title`, `text`, `label`, `cell`, ...). There is no plain
string kind, so a catalogue cannot define text that a later safety check would miss.

## Development

```
uv sync
uv run pytest -q
uv run ruff check . && uv run ruff format --check . && uv run mypy
git config core.hooksPath scripts/hooks     # refuses commit messages with tool attribution
```

Changes go on a branch and a pull request. Releases are made by release-please from the
commit messages (Conventional Commits) and published to PyPI by trusted publishing.
