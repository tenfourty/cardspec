from __future__ import annotations

import pytest

from cardspec import LinkPolicy


def check(url, kind="link", **kw):
    r = LinkPolicy(**kw).check(url, kind)
    return None if r is None else r[0]


@pytest.mark.parametrize(
    "url",
    [
        "https://dash.example.com/web",
        "https://example.com",
        "https://example.com:8443/a?b=c#d",
        "https://A.Example.COM/x",
    ],
)
def test_good_links(url):
    assert check(url) is None


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "javascript:alert(1)",
        "data:text/html,hi",
        "file:///etc/passwd",
        "//example.com/x",
        "/relative",
        "example.com",
        "https://user@example.com/",
        "https://user:pw@example.com/",
        "https://localhost/",
        "https://app.localhost/",
        "https://intranet/",
        "https://127.0.0.1/",
        "https://10.0.0.5/x",
        "https://[::1]/",
        "https://[2001:db8::1]/",
        "https://2130706433/",
        "https://0x7f.0.0.1/",
        "https://xn--e1afmkfd.example.com/",
        "https://exämple.com/",
        "https://example.com\\@evil.test/",
        "https://exa mple.com/",
        "https://example.com/a\nb",
        "https://example.com:99999/",
        "https://example.com:abc/",
        "https://.example.com/",
        "https://example..com/",
        "https://",
        "",
    ],
)
def test_bad_links(url):
    assert check(url) == "bad_url"


def test_non_string_is_bad():
    assert check(5) == "bad_url"  # type: ignore[arg-type]


def test_link_hosts_open_by_default_and_listable():
    assert check("https://other.example.org/x") is None
    assert check("https://other.example.org/x", allowed_hosts={"dash.example.com"}) == (
        "host_not_allowed"
    )
    assert check("https://DASH.example.com/x", allowed_hosts={"dash.example.com"}) is None


def test_link_hosts_may_be_a_callable():
    assert check("https://a.example.com/", allowed_hosts=lambda h: h.startswith("a.")) is None
    assert check("https://b.example.com/", allowed_hosts=lambda h: h.startswith("a.")) == (
        "host_not_allowed"
    )


def test_pictures_need_a_configured_host():
    assert check("https://img.example.com/a.png", "image") == "image_host_not_allowed"
    assert check("https://img.example.com/a.png", "image", image_hosts=()) == (
        "image_host_not_allowed"
    )
    assert check("https://img.example.com/a.png", "image", image_hosts={"img.example.com"}) is None
    assert check("https://other.example.com/a.png", "image", image_hosts={"img.example.com"}) == (
        "image_host_not_allowed"
    )


def test_picture_host_wildcard_matches_subdomains_only():
    kw = {"image_hosts": {"*.cdn.example.com"}}
    assert check("https://a.cdn.example.com/x.png", "image", **kw) is None
    assert check("https://cdn.example.com/x.png", "image", **kw) == "image_host_not_allowed"
    assert check("https://evilcdn.example.com/x.png", "image", **kw) == "image_host_not_allowed"


def test_picture_still_needs_a_sound_address():
    assert check("http://img.example.com/a.png", "image", image_hosts={"img.example.com"}) == (
        "bad_url"
    )


def test_picture_host_list_does_not_open_buttons_and_vice_versa():
    assert check("https://img.example.com/a", "link", image_hosts={"img.example.com"}) is None
    assert (
        check("https://img.example.com/a.png", "image", allowed_hosts={"img.example.com"})
        == "image_host_not_allowed"
    )


def test_unknown_kind_is_an_error():
    with pytest.raises(ValueError):
        LinkPolicy().check("https://example.com", "video")
