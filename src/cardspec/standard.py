# Derived from json-render's catalogue design, rewritten in Python; see the NOTICE file.
"""The standard catalogue: Card, Section, Text, Fields, Table, Chart, Divider, Image, Actions."""

from __future__ import annotations

from typing import Any

from .catalogue import Catalogue, Element
from .schema import Children, Ctx, Enum, List, Num, Obj, Opt, Str, Url

_BODY = ("Section", "Text", "Fields", "Table", "Chart", "Divider", "Image", "Actions")


def _plural(n: int, noun: str) -> str:
    if n == 1:
        return f"{n} {noun}"
    return f"{n} {noun[:-1]}ies" if noun.endswith("y") else f"{n} {noun}s"


def _check_table(props: dict[str, Any], path: str, ctx: Ctx) -> None:
    headers = props["headers"]
    for i, row in enumerate(props.get("rows", [])):
        if len(row) != len(headers):
            ctx.issue(
                f"{path}/rows/{i}",
                "row_width",
                f"row {i} (counting from 0) has {_plural(len(row), 'cell')}, the table has "
                f"{_plural(len(headers), 'header')}",
                len(headers),
                len(row),
            )
    align = props.get("align")
    if align is not None and len(align) != len(headers):
        ctx.issue(
            f"{path}/align",
            "align_width",
            f"align has {_plural(len(align), 'entry')} but the table has "
            f"{_plural(len(headers), 'header')}; give one per column",
            len(headers),
            len(align),
        )


def _check_chart(props: dict[str, Any], path: str, ctx: Ctx) -> None:
    kind = props["kind"]
    final = ctx.mode == "final"
    if kind == "pie":
        for forbidden in ("categories", "series"):
            if forbidden in props:
                ctx.issue(
                    f"{path}/{forbidden}",
                    "chart_shape",
                    f"a pie chart takes segments, not {forbidden}; remove {forbidden}",
                )
        if final and not props.get("segments"):
            ctx.issue(f"{path}/segments", "chart_shape", "a pie chart needs one or more segments")
        return
    if "segments" in props:
        ctx.issue(
            f"{path}/segments",
            "chart_shape",
            f"a {kind} chart takes categories and series, not segments; remove segments",
        )
    if final:
        for needed in ("categories", "series"):
            if not props.get(needed):
                ctx.issue(
                    f"{path}/{needed}",
                    "chart_shape",
                    f"a {kind} chart needs {needed} with one or more entries",
                )
    categories = props.get("categories", [])
    for i, series in enumerate(props.get("series", [])):
        if len(series["values"]) != len(categories):
            ctx.issue(
                f"{path}/series/{i}/values",
                "series_length",
                f"series {i} has {_plural(len(series['values']), 'value')} but there are "
                f"{_plural(len(categories), 'category')}; give one value per category",
                len(categories),
                len(series["values"]),
            )


_CARD = Element(
    "Card",
    props={
        "title": Str("title", max="title"),
        "subtitle": Opt(Str("subtitle", max="subtitle")),
    },
    children=Children(_BODY),
    description=(
        "The whole card, and always the first element. It has a title, an optional subtitle "
        "and the elements that make up the body."
    ),
    example={
        "type": "Card",
        "v": 1,
        "title": "Deploy: web 2026.11.8",
        "subtitle": "Finished 14:02",
        "children": [{"type": "Text", "content": "All checks passed."}],
    },
)

_SECTION = Element(
    "Section",
    props={"title": Opt(Str("title", max="title"))},
    children=Children(tuple(c for c in _BODY if c != "Section")),
    description=(
        "Groups some elements under an optional heading. One level only: no Section inside "
        "a Section."
    ),
    example={
        "type": "Section",
        "title": "Checks",
        "children": [{"type": "Text", "content": "Everything is green."}],
    },
)

_TEXT = Element(
    "Text",
    props={
        "content": Str("text", max="text", multiline=True),
        "style": Opt(Enum("plain", "bold", "muted")),
    },
    description=(
        "A paragraph. Only **bold**, _italic_ and `code` are marked up; everything else is "
        "shown exactly as written. No links and no headings."
    ),
    example={"type": "Text", "content": "**Healthy.** One slow migration.", "style": "plain"},
)

_FIELDS = Element(
    "Fields",
    props={
        "items": List(
            Obj(
                {
                    "label": Str("label", max="field_label"),
                    "value": Str("value", max="field_value", allow_empty=True, number_ok=True),
                }
            ),
            max="fields_items",
            min=1,
        )
    },
    description="A grid of a few labelled values, such as numbers or states.",
    example={
        "type": "Fields",
        "items": [
            {"label": "Errors (1h)", "value": 0},
            {"label": "p95 latency", "value": "212 ms"},
        ],
    },
)

_TABLE = Element(
    "Table",
    props={
        "headers": List(Str("header", max="cell"), max="table_cols", min=1),
        "rows": List(
            List(Str("cell", max="cell", allow_empty=True, number_ok=True), max="table_cols"),
            max="table_rows",
        ),
        "align": Opt(List(Enum("left", "center", "right"), max="table_cols")),
        "caption": Opt(Str("caption", max="subtitle")),
    },
    check=_check_table,
    description=(
        "Rows and columns. Every row has exactly one cell per header. A card holds at most "
        "one table."
    ),
    example={
        "type": "Table",
        "headers": ["Step", "Result", "Seconds"],
        "rows": [["build", "ok", 61], ["migrate", "ok (slow)", 94]],
        "align": ["left", "left", "right"],
    },
)

_CHART = Element(
    "Chart",
    props={
        "title": Str("title", max="title"),
        "kind": Enum("bar", "line", "area", "pie"),
        "categories": Opt(List(Str("category", max="chart_label"), max="chart_categories")),
        "series": Opt(
            List(
                Obj(
                    {
                        "name": Str("series", max="chart_label"),
                        "values": List(Num(), max="chart_categories"),
                    }
                ),
                max="chart_series",
            )
        ),
        "segments": Opt(
            List(
                Obj({"label": Str("segment", max="chart_label"), "value": Num(positive=True)}),
                max="chart_categories",
            )
        ),
    },
    check=_check_chart,
    description=(
        "A chart of numbers. For bar, line and area give categories and one or more series with "
        "one value per category. For pie give segments (each value greater than zero)."
    ),
    example={
        "type": "Chart",
        "title": "Errors per hour",
        "kind": "bar",
        "categories": ["12", "13", "14"],
        "series": [{"name": "errors", "values": [2, 1, 0]}],
    },
)

_DIVIDER = Element(
    "Divider",
    props={},
    description="A thin line between parts of the card.",
    example={"type": "Divider"},
)

_IMAGE = Element(
    "Image",
    props={"url": Url("image"), "alt": Str("alt", max="alt")},
    description=(
        "A picture. The address must be https and on a host the deployment allows; the alt text "
        "says what the picture shows."
    ),
    example={"type": "Image", "url": "https://img.example.com/chart.png", "alt": "Latency chart"},
)

_ACTIONS = Element(
    "Actions",
    props={
        "buttons": List(
            Obj({"label": Str("button", max="button_label"), "url": Url("link")}),
            max="buttons",
            min=1,
        )
    },
    description="Buttons that open a web address. This is the only place a link may go.",
    example={
        "type": "Actions",
        "buttons": [{"label": "Open dashboard", "url": "https://dash.example.com/web"}],
    },
)

RULES: tuple[str, ...] = (
    'The first element is a Card with "v": 1 and a title.',
    "Use Fields for a few numbers, Table for rows, Chart for a trend or a share, and Actions "
    "for next steps.",
    "Text takes only **bold**, _italic_ and `code`; everything else is shown as written.",
    "Links go only in Actions buttons; never put a link in text.",
    "Every Chart series has one value per category.",
    "A card is fixed once written: there are no states, repeats or conditions.",
    "Nothing is shortened for you. A card over a limit is refused with a list of issues; fix "
    "them and send the card again.",
)

_EXAMPLE: dict[str, Any] = {
    "type": "Card",
    "v": 1,
    "title": "Deploy: web 2026.11.8",
    "subtitle": "Finished 14:02, 3 minutes",
    "children": [
        {"type": "Text", "content": "**Healthy.** All checks passed; one slow migration."},
        {
            "type": "Fields",
            "items": [
                {"label": "Version", "value": "2026.11.8"},
                {"label": "Errors (1h)", "value": 0},
            ],
        },
        {
            "type": "Table",
            "headers": ["Step", "Result", "Seconds"],
            "rows": [["build", "ok", 61], ["migrate", "ok (slow)", 94], ["smoke", "ok", 12]],
            "align": ["left", "left", "right"],
        },
        {
            "type": "Chart",
            "title": "Errors per hour",
            "kind": "bar",
            "categories": ["12", "13", "14"],
            "series": [{"name": "errors", "values": [2, 1, 0]}],
        },
        {"type": "Divider"},
        {
            "type": "Actions",
            "buttons": [{"label": "Open dashboard", "url": "https://dash.example.com/web"}],
        },
    ],
}

CATALOGUE = Catalogue(
    [_CARD, _SECTION, _TEXT, _FIELDS, _TABLE, _CHART, _DIVIDER, _IMAGE, _ACTIONS],
    root="Card",
    versions=(1,),
    rules=RULES,
    example=_EXAMPLE,
    profiles={
        # Slack-safe: the library defaults.
        "slack": {},
        # A web page can hold a bigger card; the same strict rules apply.
        "page": {
            "limits": {
                "max_bytes": 256 * 1024,
                "max_chars": 40000,
                "max_elements": 200,
                "text": 20000,
                "cell": 1000,
                "fields_items": 50,
                "table_rows": 500,
                "table_cols": 20,
                "chart_categories": 60,
                "chart_series": 8,
                "buttons": 20,
                "max_per_type": {"Table": 20},
            }
        },
        # A terminal cannot show pictures.
        "terminal": {
            "elements": [
                n
                for n in (
                    "Card",
                    "Section",
                    "Text",
                    "Fields",
                    "Table",
                    "Chart",
                    "Divider",
                    "Actions",
                )
            ]
        },
    },
)
