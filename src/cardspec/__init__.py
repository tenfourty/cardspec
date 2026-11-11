"""cardspec: describe a small card as data, check it, and show it on any surface.

Inspired by and derived from json-render (Apache-2.0); see the NOTICE file.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .catalogue import Catalogue, Element, Profile
from .escape import escape_mrkdwn
from .issue import CardError, Issue
from .limits import Limits
from .links import LinkPolicy
from .parse import parse
from .prompt import catalogue_prompt
from .slack import SlackResult, render_slack
from .standard import CATALOGUE as STANDARD
from .validate import validate

try:
    __version__ = version("cardspec")
except PackageNotFoundError:  # not installed, for example run from a source tree
    __version__ = "0.0.0"

__all__ = [
    "STANDARD",
    "CardError",
    "Catalogue",
    "Element",
    "Issue",
    "Limits",
    "LinkPolicy",
    "Profile",
    "SlackResult",
    "__version__",
    "catalogue_prompt",
    "escape_mrkdwn",
    "parse",
    "render_slack",
    "validate",
]
