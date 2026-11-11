"""Turn a valid card into Slack Block Kit blocks.

`render_slack` checks the card first (with `validate`), then builds the blocks. It never cuts
anything short: a card that is invalid, or that would break one of Slack's own limits, comes
back as a list of `Issue`s and no blocks at all, so whoever wrote the card can fix it.

Every string from the card is escaped, wherever it goes (see `escape_mrkdwn`). Card text is
plain text except in `Text` elements, where `**bold**`, `_italic_` and `` `code` `` are turned
into Slack's own marks; any other mark character (`*`, `_`, `~`, a backtick) is made harmless
by a zero-width space after it, because Slack has no backslash escape. Links come only from
buttons that `LinkPolicy` has checked, and pictures only from hosts the caller listed.

A Chart becomes Slack's `data_visualization` block. A chart that is over a limit is refused;
it is never turned into a table.

Where each limit comes from (check them again here if Slack changes):

* https://docs.slack.dev/reference/block-kit/blocks/table-block
* https://docs.slack.dev/reference/block-kit/blocks/data-visualization-block
* https://docs.slack.dev/reference/block-kit/blocks/section-block
* https://docs.slack.dev/reference/block-kit/blocks/context-block
* https://docs.slack.dev/reference/block-kit/blocks/actions-block
* https://docs.slack.dev/reference/block-kit/blocks/image-block
* https://docs.slack.dev/reference/block-kit/block-elements/button-element
* https://docs.slack.dev/reference/block-kit/composition-objects/text-object
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .catalogue import Catalogue, Profile
from .escape import escape_mrkdwn
from .issue import CardError, Issue, pointer
from .limits import Limits
from .links import LinkPolicy
from .parse import parse
from .validate import validate

# Slack's own limits, which hold whatever the card's `Limits` say.
MAX_BLOCKS = 50
MAX_SECTION_TEXT = 3000
MAX_CONTEXT_TEXT = 3000
MAX_FIELDS = 10
MAX_FIELD_TEXT = 2000
MAX_BUTTONS = 25
MAX_BUTTON_TEXT = 75
MAX_BUTTON_URL = 3000
MAX_IMAGE_URL = 3000
MAX_ALT_TEXT = 2000
MAX_TABLE_ROWS = 100  # the header row counts
MAX_TABLE_COLS = 20
MAX_TABLE_CHARS = 10000  # across all cells of all tables in one message
MAX_CHARTS = 2
MAX_CHART_TITLE = 50
MAX_CHART_LABEL = 20
MAX_CHART_SERIES = 12
MAX_CHART_SEGMENTS = 12
MAX_CHART_POINTS = 20  # data points in one series, so categories too

_ZWSP = "​"
_MARKS = re.compile(r"([*_~`])")
_SPAN = re.compile(
    r"\*\*(?=\S)(?P<bold>[^\n]+?)(?<=\S)\*\*"
    r"|`(?P<code>[^`\n]+)`"
    r"|(?<!\w)_(?=\S)(?P<italic>[^_\n]+?)(?<=\S)_(?!\w)"
)


@dataclass(frozen=True)
class SlackResult:
    """What `render_slack` returns: blocks and a fallback text, or the issues that stop them."""

    blocks: list[dict[str, Any]] = field(default_factory=list)
    text: str = ""
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def _safe(text: str) -> str:
    """Escape for Slack and make mark characters harmless (for text that is not markup)."""
    return _MARKS.sub(r"\1" + _ZWSP, escape_mrkdwn(text))


def _plain(value: object) -> str:
    """A card value as text: numbers become their usual text."""
    return value if isinstance(value, str) else str(value)


def _render_text(content: str, *, in_bold: bool) -> str:
    """Card text to mrkdwn. Marked-up spans become Slack marks; everything else is defused."""
    out: list[str] = []
    pos = 0
    for m in _SPAN.finditer(content):
        out.append(_safe(content[pos : m.start()]))
        pos = m.end()
        if m.group("bold") is not None:
            inner = _safe(m.group("bold"))
            out.append(inner if in_bold else f"*{inner}*")
        elif m.group("code") is not None:
            out.append(f"`{escape_mrkdwn(m.group('code'))}`")
        else:
            out.append(f"_{_safe(m.group('italic'))}_")
    out.append(_safe(content[pos:]))
    return "".join(out)


def _bold_lines(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        core = line.strip()
        if not core:
            lines.append(line)
            continue
        lead = line[: len(line) - len(line.lstrip())]
        trail = line[len(line.rstrip()) :]
        lines.append(f"{lead}*{core}*{trail}")
    return "\n".join(lines)


class _Run:
    def __init__(self, flat: dict[str, Any], limits: Limits) -> None:
        self.elements: dict[str, Any] = flat["elements"]
        self.limits = limits
        self.issues: list[Issue] = []
        self.blocks: list[dict[str, Any]] = []
        self.table_chars = 0
        self.charts = 0

    # -- helpers -----------------------------------------------------------------------------

    def issue(
        self,
        path: str,
        code: str,
        message: str,
        limit: int | None = None,
        actual: int | None = None,
    ) -> None:
        self.issues.append(Issue(path, code, message, limit, actual))

    def fit(self, text: str, limit: int, path: str, what: str) -> str:
        if len(text) > limit:
            self.issue(
                path,
                "slack_text_too_long",
                f"the {what} is {len(text)} characters once escaped for Slack; Slack's limit is "
                f"{limit}. Make it shorter",
                limit,
                len(text),
            )
        return text

    def mrkdwn_section(self, text: str, limit: int, path: str, what: str) -> dict[str, Any]:
        return {
            "type": "section",
            "text": {"type": "mrkdwn", "text": self.fit(text, limit, path, what)},
        }

    def context(self, text: str, path: str, what: str) -> dict[str, Any]:
        text = self.fit(text, MAX_CONTEXT_TEXT, path, what)
        return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}

    def heading(self, title: str, path: str) -> dict[str, Any]:
        return self.mrkdwn_section(f"*{_safe(title)}*", MAX_SECTION_TEXT, path, "title")

    # -- elements ----------------------------------------------------------------------------

    def walk(self, key: str) -> None:
        node = self.elements[key]
        props: dict[str, Any] = node.get("props", {})
        path = pointer("elements", key, "props")
        handler: Callable[[dict[str, Any], str], None] | None = getattr(
            self, "_" + str(node["type"]).lower(), None
        )
        if handler is None:
            self.issue(
                pointer("elements", key, "type"),
                "element_not_rendered",
                f"{node['type']} cannot be shown in Slack yet; remove it",
            )
        else:
            handler(props, path)
        for child in node.get("children", []):
            self.walk(child)

    def _card(self, props: dict[str, Any], path: str) -> None:
        title = _safe(props["title"])
        self.blocks.append(
            self.mrkdwn_section(f"*{title}*", MAX_SECTION_TEXT, path + "/title", "title")
        )
        if props.get("subtitle"):
            self.blocks.append(
                self.context(
                    _render_text(props["subtitle"], in_bold=False), path + "/subtitle", "subtitle"
                )
            )

    def _section(self, props: dict[str, Any], path: str) -> None:
        if props.get("title"):
            self.blocks.append(self.heading(props["title"], path + "/title"))

    def _text(self, props: dict[str, Any], path: str) -> None:
        style = props.get("style", "plain")
        path += "/content"
        if style == "bold":
            text = _bold_lines(_render_text(props["content"], in_bold=True))
        else:
            text = _render_text(props["content"], in_bold=False)
        if style == "muted":
            self.blocks.append(self.context(text, path, "text"))
        else:
            self.blocks.append(self.mrkdwn_section(text, MAX_SECTION_TEXT, path, "text"))

    def _fields(self, props: dict[str, Any], path: str) -> None:
        items = props["items"]
        if len(items) > MAX_FIELDS:
            self.issue(
                path + "/items",
                "slack_too_many_fields",
                f"has {len(items)} items; Slack shows at most {MAX_FIELDS} in one group. "
                "Split them into two Fields or use a Table",
                MAX_FIELDS,
                len(items),
            )
        fields = []
        for i, item in enumerate(items):
            text = f"*{_safe(item['label'])}*"
            value = _plain(item["value"])
            if value:
                text += f"\n{_safe(value)}"
            fields.append(
                {
                    "type": "mrkdwn",
                    "text": self.fit(text, MAX_FIELD_TEXT, f"{path}/items/{i}", "field"),
                }
            )
        self.blocks.append({"type": "section", "fields": fields})

    def _table(self, props: dict[str, Any], path: str) -> None:
        headers = props["headers"]
        rows = props.get("rows", [])
        if len(rows) + 1 > MAX_TABLE_ROWS:
            self.issue(
                path + "/rows",
                "slack_table_too_large",
                f"has {len(rows)} rows and a header row; Slack's limit is {MAX_TABLE_ROWS} rows "
                "in all. Remove rows",
                MAX_TABLE_ROWS,
                len(rows) + 1,
            )
        if len(headers) > MAX_TABLE_COLS:
            self.issue(
                path + "/headers",
                "slack_table_too_large",
                f"has {len(headers)} columns; Slack's limit is {MAX_TABLE_COLS}. Remove columns",
                MAX_TABLE_COLS,
                len(headers),
            )

        def cell(value: object) -> dict[str, str]:
            text = escape_mrkdwn(_plain(value))
            self.table_chars += len(text)
            return {"type": "raw_text", "text": text}

        block: dict[str, Any] = {
            "type": "table",
            "rows": [[cell(h) for h in headers], *([cell(c) for c in row] for row in rows)],
        }
        if props.get("align"):
            block["column_settings"] = [{"align": a} for a in props["align"]]
        self.blocks.append(block)
        if props.get("caption"):
            self.blocks.append(self.context(_safe(props["caption"]), path + "/caption", "caption"))

    def _chart(self, props: dict[str, Any], path: str) -> None:
        self.charts += 1
        if self.charts == MAX_CHARTS + 1:
            self.issue(
                path,
                "slack_too_many_charts",
                f"Slack allows {MAX_CHARTS} charts in one message; remove the others",
                MAX_CHARTS,
                self.charts,
            )
        title = self.fit(
            escape_mrkdwn(props["title"]), MAX_CHART_TITLE, path + "/title", "chart title"
        )
        kind = props["kind"]

        def label(text: str, where: str, what: str) -> str:
            return self.fit(escape_mrkdwn(text), MAX_CHART_LABEL, where, what)

        chart: dict[str, Any]
        if kind == "pie":
            segments = props["segments"]
            self.too_big(path + "/segments", len(segments), MAX_CHART_SEGMENTS, "segments")
            chart = {
                "type": "pie",
                "segments": [
                    {
                        "label": label(g["label"], f"{path}/segments/{i}/label", "segment label"),
                        "value": g["value"],
                    }
                    for i, g in enumerate(segments)
                ],
            }
        else:
            categories = [
                label(c, f"{path}/categories/{i}", "category")
                for i, c in enumerate(props["categories"])
            ]
            series = props["series"]
            self.too_big(path + "/categories", len(categories), MAX_CHART_POINTS, "categories")
            self.too_big(path + "/series", len(series), MAX_CHART_SERIES, "series")
            names = [
                label(x["name"], f"{path}/series/{i}/name", "series name")
                for i, x in enumerate(series)
            ]
            for what, items in (("categories", categories), ("series names", names)):
                if len(set(items)) != len(items):
                    self.issue(
                        path,
                        "slack_chart_names_not_unique",
                        f"the {what} must all be different once escaped for Slack",
                    )
            chart = {
                "type": kind,
                "series": [
                    {
                        "name": name,
                        "data": [
                            {"label": c, "value": v}
                            for c, v in zip(categories, x["values"], strict=True)
                        ],
                    }
                    for name, x in zip(names, series, strict=True)
                ],
                "axis_config": {"categories": categories},
            }
        self.blocks.append({"type": "data_visualization", "title": title, "chart": chart})

    def too_big(self, path: str, actual: int, limit: int, what: str) -> None:
        if actual > limit:
            self.issue(
                path,
                "slack_chart_too_large",
                f"has {actual} {what}; Slack's limit for a chart is {limit}. Remove some",
                limit,
                actual,
            )

    def _divider(self, props: dict[str, Any], path: str) -> None:
        self.blocks.append({"type": "divider"})

    def _image(self, props: dict[str, Any], path: str) -> None:
        url = self.fit(props["url"], MAX_IMAGE_URL, path + "/url", "picture address")
        alt = self.fit(escape_mrkdwn(props["alt"]), MAX_ALT_TEXT, path + "/alt", "alt text")
        self.blocks.append({"type": "image", "image_url": url, "alt_text": alt})

    def _actions(self, props: dict[str, Any], path: str) -> None:
        buttons = props["buttons"]
        if len(buttons) > MAX_BUTTONS:
            self.issue(
                path + "/buttons",
                "slack_too_many_buttons",
                f"has {len(buttons)} buttons; Slack's limit is {MAX_BUTTONS}. Remove some",
                MAX_BUTTONS,
                len(buttons),
            )
        elements = []
        for i, b in enumerate(buttons):
            here = f"{path}/buttons/{i}"
            label = self.fit(
                escape_mrkdwn(b["label"]), MAX_BUTTON_TEXT, here + "/label", "button label"
            )
            url = self.fit(b["url"], MAX_BUTTON_URL, here + "/url", "button address")
            # A link button only: no action id and no value, so a click is never sent back.
            elements.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": label, "emoji": False},
                    "url": url,
                }
            )
        self.blocks.append({"type": "actions", "elements": elements})


def render_slack(
    card: Any,
    *,
    catalogue: Catalogue | None = None,
    limits: Limits | None = None,
    links: LinkPolicy | None = None,
    profile: str | Profile | None = None,
) -> SlackResult:
    """Render `card` (flat or nested form, or its JSON text) as Slack blocks.

    The card is checked first with `validate` (same `catalogue`, `limits`, `links`; `profile`
    defaults to the catalogue's `slack` profile when it has one). If anything is wrong, or the
    result would break one of Slack's limits, the result has `issues` and no blocks.
    """
    if catalogue is None:
        from .standard import CATALOGUE

        catalogue = CATALOGUE
    if profile is None and "slack" in catalogue.profiles:
        profile = "slack"
    try:
        flat = parse(card, limits=limits) if not _is_flat(card) else card
    except CardError as exc:
        return SlackResult(issues=exc.issues)
    issues = validate(flat, catalogue=catalogue, limits=limits, links=links, profile=profile)
    if issues:
        return SlackResult(issues=issues)

    prof = catalogue.profile(profile) if isinstance(profile, str) else profile
    run = _Run(flat, limits or (prof.limits if prof else Limits()))
    run.walk(flat["root"])
    if len(run.blocks) > MAX_BLOCKS:
        run.issue(
            "",
            "slack_too_many_blocks",
            f"makes {len(run.blocks)} Slack blocks; Slack's limit is {MAX_BLOCKS} in one message. "
            "Remove parts of the card",
            MAX_BLOCKS,
            len(run.blocks),
        )
    if run.table_chars > MAX_TABLE_CHARS:
        run.issue(
            "",
            "slack_table_too_large",
            f"the tables hold {run.table_chars} characters once escaped for Slack; Slack's limit "
            f"is {MAX_TABLE_CHARS} across all tables in one message. Remove rows or shorten cells",
            MAX_TABLE_CHARS,
            run.table_chars,
        )
    if run.issues:
        return SlackResult(issues=run.issues)
    title = _safe(flat["elements"][flat["root"]]["props"]["title"])
    return SlackResult(blocks=run.blocks, text=title)


def _is_flat(card: Any) -> bool:
    return isinstance(card, dict) and ("elements" in card or "root" in card)
