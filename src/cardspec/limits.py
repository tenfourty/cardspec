"""Sizes a card must stay inside. Everything is configurable; the defaults are safe for Slack.

A limit is never applied by cutting text off: a card over a limit is refused with an `Issue`,
so whoever wrote it can fix it.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


def _default_per_type() -> Mapping[str, int]:
    return {"Table": 1}


@dataclass(frozen=True)
class Limits:
    # the document
    max_bytes: int = 32 * 1024  # size of the JSON text, checked before anything walks it
    max_json_depth: int = 12  # how deeply JSON arrays and objects may nest
    max_chars: int = 4000  # all text in the card, orphans included; web addresses do not count
    max_elements: int = 40  # len(elements), reachable or not
    max_nesting: int = 3  # elements from the Card down to a leaf (Card, Section, Text is 3)
    max_per_type: Mapping[str, int] = field(default_factory=_default_per_type)
    # strings
    title: int = 150
    subtitle: int = 300
    text: int = 2000
    field_label: int = 60
    field_value: int = 200
    cell: int = 200
    chart_label: int = 24
    button_label: int = 40
    alt: int = 200
    url: int = 2000
    image_url: int = 1000
    # counts
    fields_items: int = 10
    table_rows: int = 50
    table_cols: int = 8
    chart_categories: int = 12
    chart_series: int = 3
    buttons: int = 5

    def __post_init__(self) -> None:
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            if f.name == "max_per_type":
                if not isinstance(value, Mapping) or any(
                    not isinstance(k, str) or isinstance(n, bool) or not isinstance(n, int) or n < 1
                    for k, n in value.items()
                ):
                    raise ValueError("max_per_type must map element names to counts of 1 or more")
                object.__setattr__(self, f.name, MappingProxyType(dict(value)))
            elif isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"limit {f.name} must be a whole number of 1 or more")

    def replace(self, **changes: object) -> Limits:
        return dataclasses.replace(self, **changes)  # type: ignore[arg-type]


#: The names a catalogue may use to refer to a number in `Limits`.
LIMIT_NAMES: frozenset[str] = frozenset(
    f.name for f in dataclasses.fields(Limits) if f.name != "max_per_type"
)
