"""Which web addresses a card may carry.

A button address is followed by a person; a picture address is fetched by the surface itself
(Slack fetches it), so an address the agent wrote can carry data out in its query part.
That is why pictures are allowed only from hosts someone listed: with none listed there are
no pictures at all.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection
from dataclasses import dataclass
from urllib.parse import urlsplit

HostRule = Collection[str] | Callable[[str], bool]

_LABEL = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?")
_TLD = re.compile(r"[a-z][a-z0-9-]*")


def _matches(rule: HostRule, host: str) -> bool:
    if callable(rule):
        return bool(rule(host))
    for pattern in rule:
        pattern = pattern.lower()
        if pattern.startswith("*."):
            if host.endswith(pattern[1:]) and host != pattern[2:]:
                return True
        elif host == pattern:
            return True
    return False


def _has_rule(rule: HostRule | None) -> bool:
    return callable(rule) or bool(rule)


@dataclass(frozen=True)
class LinkPolicy:
    """Rules for the web addresses in a card.

    Always: https only; no user name or password; a real public-looking host name (no IP
    address, no `localhost`, no single-label name, no punycode or non-ASCII name); only
    printable ASCII in the whole address.

    `allowed_hosts`: if set, button addresses must be on one of these hosts. Entries are exact
    host names or `*.suffix` for subdomains; a callable taking the lower-case host is also
    accepted. `None` means any host that passes the rules above.

    `image_hosts`: the only hosts a picture may come from, in the same form. Empty (the
    default) means no pictures at all.
    """

    allowed_hosts: HostRule | None = None
    image_hosts: HostRule = ()

    @property
    def pictures_allowed(self) -> bool:
        return _has_rule(self.image_hosts)

    def check(self, url: object, kind: str = "link") -> tuple[str, str] | None:
        """Return None if `url` is acceptable, else `(code, message)`.

        A host rule that is a callable and raises does not escape from here: the address is
        refused with the code `link_policy_error`, so a card with an address that cannot be
        checked is never accepted and never crashes the caller.
        """
        if kind not in ("link", "image"):
            raise ValueError(f"unknown address kind {kind!r}; use 'link' or 'image'")
        try:
            return self._check(url, kind)
        except Exception as exc:
            return (
                "link_policy_error",
                f"the web address could not be checked because the host rule failed "
                f"({type(exc).__name__}); it is refused",
            )

    def _check(self, url: object, kind: str) -> tuple[str, str] | None:
        what = "picture address" if kind == "image" else "web address"
        host_or_error = self._host(url, what)
        if isinstance(host_or_error, tuple):
            return host_or_error
        host = host_or_error
        # A host list names hosts, not ports: an address with a port is never let through
        # because its host is listed (a port can reach some other service on that host).
        if (kind == "image" or self.allowed_hosts is not None) and ":" in urlsplit(str(url)).netloc:
            return (
                "port_not_allowed",
                f"the {what} must not give a port; remove the ':' and the number",
            )
        if kind == "image":
            if not self.pictures_allowed:
                return (
                    "image_host_not_allowed",
                    "pictures are not available here (no picture hosts are configured); "
                    "remove the Image",
                )
            if not _matches(self.image_hosts, host):
                return (
                    "image_host_not_allowed",
                    f"pictures may not come from {host}; use a picture on an allowed host",
                )
        elif self.allowed_hosts is not None and not _matches(self.allowed_hosts, host):
            return (
                "host_not_allowed",
                f"links to {host} are not allowed; use an address on an allowed host",
            )
        return None

    @staticmethod
    def _host(url: object, what: str) -> str | tuple[str, str]:
        def bad(why: str) -> tuple[str, str]:
            return ("bad_url", f"the {what} {why}")

        if not isinstance(url, str) or not url:
            return bad("must be a non-empty string")
        if any(not 0x21 <= ord(c) <= 0x7E for c in url) or "\\" in url:
            return bad(
                "may hold only printable ASCII with no spaces or backslashes "
                "(percent-encode anything else)"
            )
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            return bad("is not a valid address")
        if parts.scheme.lower() != "https":
            return bad("must start with https://")
        netloc = parts.netloc
        if not netloc:
            return bad("has no host")
        if "@" in netloc:
            return bad("must not contain a user name or password")
        if netloc.startswith("["):
            return bad("must use a host name, not an IP address")
        if port is not None and not 1 <= port <= 65535:
            return bad("has a port that is out of range")
        host = netloc.rsplit(":", 1)[0].lower() if ":" in netloc else netloc.lower()
        labels = host.split(".")
        if len(host) > 253 or len(labels) < 2 or any(not _LABEL.fullmatch(x) for x in labels):
            return bad("must use a full host name such as www.example.com")
        if not _TLD.fullmatch(labels[-1]):
            return bad("must use a host name, not an IP address")
        if host == "localhost" or host.endswith(".localhost"):
            return bad("must not point at localhost")
        if any(x.startswith("xn--") for x in labels):
            return bad("must not use an international (punycode) host name")
        return host
