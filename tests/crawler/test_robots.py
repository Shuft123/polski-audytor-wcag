import io
import urllib.error

import pytest

from audytor.crawler import robots
from audytor.crawler.robots import (
    STATUS_IGNORED,
    STATUS_MISSING,
    STATUS_UNREACHABLE,
    RobotsCache,
    fetch_robots,
    parse_robots,
    robots_url_for,
)

ROBOTS_TXT = """
User-agent: *
Disallow: /admin/
Disallow: /szukaj
Allow: /admin/publiczne/

User-agent: PolskiAudytorWCAG
Disallow: /prywatne/
Crawl-delay: 3
"""


def test_robots_url_for():
    assert robots_url_for("https://www.przyklad.pl/a/b?c=1#d") == "https://www.przyklad.pl/robots.txt"
    assert robots_url_for("http://localhost:8000/x") == "http://localhost:8000/robots.txt"


def test_rules_for_our_user_agent_take_precedence():
    policy = parse_robots(ROBOTS_TXT, "https://przyklad.pl/robots.txt")
    # Mamy własną sekcję, więc reguły z "*" nas nie dotyczą.
    assert not policy.can_fetch("https://przyklad.pl/prywatne/plik")
    assert policy.can_fetch("https://przyklad.pl/admin/")
    assert policy.crawl_delay() == 3.0


def test_wildcard_rules_apply_when_no_own_section():
    policy = parse_robots("User-agent: *\nDisallow: /admin/\n", "https://przyklad.pl/robots.txt")
    assert not policy.can_fetch("https://przyklad.pl/admin/panel")
    assert policy.can_fetch("https://przyklad.pl/")
    assert policy.crawl_delay() is None


def test_disallow_all():
    policy = parse_robots("User-agent: *\nDisallow: /\n", "https://przyklad.pl/robots.txt")
    assert not policy.can_fetch("https://przyklad.pl/")


def test_empty_file_allows_everything():
    policy = parse_robots("", "https://przyklad.pl/robots.txt")
    assert policy.can_fetch("https://przyklad.pl/cokolwiek")


def _raise(exc):
    def fake_urlopen(*args, **kwargs):
        raise exc
    return fake_urlopen


@pytest.mark.parametrize("code", [401, 403, 404, 410])
def test_4xx_means_no_restrictions(monkeypatch, code):
    err = urllib.error.HTTPError("https://p.pl/robots.txt", code, "x", {}, io.BytesIO())
    monkeypatch.setattr(robots.urllib.request, "urlopen", _raise(err))
    policy = fetch_robots("https://p.pl/", user_agent="test")
    assert policy.status == STATUS_MISSING
    assert policy.can_fetch("https://p.pl/cokolwiek")


@pytest.mark.parametrize(
    "exc",
    [
        urllib.error.HTTPError("https://p.pl/robots.txt", 503, "x", {}, io.BytesIO()),
        urllib.error.URLError("brak połączenia"),
        TimeoutError("timeout"),
    ],
)
def test_5xx_or_network_error_blocks_everything(monkeypatch, exc):
    monkeypatch.setattr(robots.urllib.request, "urlopen", _raise(exc))
    policy = fetch_robots("https://p.pl/", user_agent="test")
    assert policy.status == STATUS_UNREACHABLE
    assert not policy.can_fetch("https://p.pl/")
    assert policy.error


def test_cache_fetches_once_per_site(monkeypatch):
    calls = []

    def fake_fetch(url, user_agent, timeout):
        calls.append(url)
        return parse_robots("User-agent: *\nDisallow: /x\n", robots_url_for(url))

    monkeypatch.setattr(robots, "fetch_robots", fake_fetch)
    cache = RobotsCache("test")
    assert cache.can_fetch("https://p.pl/a")
    assert not cache.can_fetch("https://p.pl/x")
    assert cache.can_fetch("https://inna.pl/a")
    assert len(calls) == 2


def test_cache_disabled_allows_everything(monkeypatch):
    monkeypatch.setattr(robots, "fetch_robots", _raise(AssertionError("nie powinno pobierać")))
    cache = RobotsCache("test", enabled=False)
    assert cache.can_fetch("https://p.pl/admin")
    assert cache.policy_for("https://p.pl/").status == STATUS_IGNORED
