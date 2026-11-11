"""Escaping that every renderer must apply to card text.

Card text is plain text. The checker accepts `&`, `<` and `>` in it, because they are ordinary
characters. Some surfaces give them meaning: in Slack, `<https://x|y>` is a link that shows
different words from where it goes, and `<@U123>` or `<!here>` is a mention. A renderer must
therefore run every text value that the surface reads as markup through the escape for that
surface before it writes it out. Places that take plain text show text as typed: not escaped.
Links come only from link elements that `LinkPolicy` has checked, never from text.
"""

from __future__ import annotations


def escape_mrkdwn(text: str) -> str:
    """Escape `&`, `<` and `>` as Slack asks, so text can never form a link or a mention.

    `&` goes first so the entities it adds are not escaped a second time.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
