# Changelog

## 0.1.1 (2026-11-12)

The first release published to PyPI. It is the same code as 0.1.0, whose tag never published: GitHub refused to start its workflow, because the allowed-actions list still named actions by tag rather than by the commits the workflow pins.

## 0.1.0 (2026-11-12)

First release. A standard-library-only library (Python 3.11 or later) for cards described as data:

- A schema kit and a catalogue of typed elements (Card, Section, Text, Fields, Table, Chart,
  Divider, Image, Actions), with a `standard` catalogue you can extend.
- `parse`, which turns the nested form of a card into the flat "root plus elements" form.
- `validate`, which returns path-addressed issues for shape, size, characters, structure and
  links, with `Limits`, `LinkPolicy` and per-surface profiles.
- `catalogue_prompt`, which generates the instructions for the model that writes a card from the
  same data that validates it.
- `render_slack`, which turns a valid card into Slack blocks and a fallback text, escapes text so
  it cannot form a link or a mention, and refuses a card that is over Slack's limits.
