import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from web_acquisition.discovery import LinkParser
from web_acquisition.models import AcquisitionError, CrawlPolicy
from web_acquisition.policy import EgressPolicy, PolicyEngine
from web_acquisition.urls import display_url, normalize


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("HTTP://Example.COM:80/a/../B#frag", "http://example.com/B"),
        ("https://example.com:443", "https://example.com/"),
        ("https://example.com/a//B", "https://example.com/a//B"),
        ("https://example.com/%7eA/%2e%2e/B", "https://example.com/B"),
        ("https://example.com/?b=2&a=1", "https://example.com/?b=2&a=1"),
        ("https://example.com/café", "https://example.com/caf%C3%A9"),
        ("https://[2001:4860:4860::8888]:443/a", "https://[2001:4860:4860::8888]/a"),
    ],
)
def test_normalization(raw, expected):
    assert normalize(raw) == expected


def test_relative_query_fragment_policies():
    assert normalize("../b#x", "https://EXAMPLE.com/a/c") == "https://example.com/b"
    assert normalize("https://example.com/a//b", collapse_slashes=True) == "https://example.com/a/b"
    assert (
        normalize("https://example.com/?b=2&a=1", query_mode="sort")
        == "https://example.com/?a=1&b=2"
    )
    assert (
        normalize("https://example.com/?secret=value", query_mode="drop") == "https://example.com/"
    )
    assert "value" not in display_url("https://example.com/?secret=value")


@pytest.mark.parametrize(
    "url",
    [
        "http://user:password@example.com/",
        "http://example.com\\@127.0.0.1/",
        "http://2130706433/",
        "http://0x7f000001/",
        "http://0177.0.0.1/",
        "http://127.1/",
        "http://%31%32%37.0.0.1/",
        "http://[fe80::1%eth0]/",
        "file:///etc/passwd",
        "https://example.com/%GG",
        "https://example.com/a%2fb",
        "https://example.com/\r\nx",
    ],
)
def test_ambiguous_or_unsafe_syntax(url):
    with pytest.raises(AcquisitionError):
        normalize(url)


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.2.3",
        "192.168.1.2",
        "169.254.169.254",
        "0.0.0.0",
        "224.0.0.1",
        "100.64.0.1",
        "192.0.2.1",
        "198.18.0.1",
        "::1",
        "::",
        "fc00::1",
        "fe80::1",
        "ff02::1",
        "::ffff:127.0.0.1",
        "64:ff9b::7f00:1",
        "2002:7f00:1::",
        "2001:db8::1",
    ],
)
def test_network_ranges(ip):
    with pytest.raises(AcquisitionError, match="ssrf_blocked"):
        EgressPolicy().validate_resolved_addresses([ip])


def test_mixed_dns_answers_fail_closed():
    with pytest.raises(AcquisitionError):
        EgressPolicy().validate_resolved_addresses(["8.8.8.8", "10.0.0.1"])
    EgressPolicy().validate_resolved_addresses(["8.8.8.8", "2001:4860:4860::8888"])


def test_domain_scope_not_suffix_confusion():
    policy = PolicyEngine(
        CrawlPolicy(
            same_origin=False,
            allowed_domains=("example.com",),
            include_subdomains=True,
            allowed_path_prefixes=("/docs/",),
            denied_path_globs=("*/private/*",),
        ),
        ["https://example.com/docs/"],
    )
    policy.check("https://a.example.com/docs/a")
    for url in (
        "https://badexample.com/docs/a",
        "https://example.com/docs/private/a",
        "https://example.com/elsewhere",
    ):
        with pytest.raises(AcquisitionError):
            policy.check(url)


def test_discovery_attributes_and_bound():
    parser = LinkParser(8)
    parser.feed(
        '<a href="a">a</a><link href="b"><img src="c"><script src="d"></script><iframe src="e"></iframe><object data="f"></object><embed src="g"><a href="h">h</a><img src="overflow">'
    )
    assert [link.url for link in parser.links] == list("abcdefgh")
    assert parser.truncated


@settings(max_examples=80, deadline=None)
@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-._~/", max_size=80))
def test_normalization_is_idempotent(path):
    normalized = normalize("https://example.com/" + path)
    assert normalize(normalized) == normalized


@settings(max_examples=40, deadline=None)
@given(st.text(max_size=2000))
def test_html_parser_never_exceeds_link_bound(text):
    parser = LinkParser(3)
    parser.feed(text)
    assert len(parser.links) <= 3


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_pages", 0),
        ("max_depth", -1),
        ("max_response_bytes", 0),
        ("request_timeout", float("inf")),
        ("concurrency", 100),
        ("max_retries", -1),
    ],
)
def test_invalid_configuration(field, value):
    with pytest.raises(ValueError):
        CrawlPolicy(**{field: value})
