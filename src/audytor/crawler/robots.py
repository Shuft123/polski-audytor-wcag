"""Obsługa robots.txt (F2) zgodnie z RFC 9309.

Zasady dla odpowiedzi serwera (RFC 9309, rozdz. 2.3.1):
- 2xx  -> parsujemy reguły,
- 4xx  -> plik "niedostępny": wolno skanować wszystko,
- 5xx / brak połączenia -> plik "nieosiągalny": NIE skanujemy niczego.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

USER_AGENT_TOKEN = "PolskiAudytorWCAG"

STATUS_OK = "ok"                    # plik pobrany i sparsowany
STATUS_MISSING = "missing"          # 4xx – brak ograniczeń
STATUS_UNREACHABLE = "unreachable"  # 5xx lub błąd sieci – blokada wszystkiego
STATUS_IGNORED = "ignored"          # sprawdzanie wyłączone przez użytkownika


def robots_url_for(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))


@dataclass
class RobotsPolicy:
    robots_url: str
    status: str
    parser: RobotFileParser | None = None
    error: str | None = None

    def can_fetch(self, url: str) -> bool:
        if self.status in (STATUS_MISSING, STATUS_IGNORED):
            return True
        if self.status == STATUS_UNREACHABLE or self.parser is None:
            return False
        return self.parser.can_fetch(USER_AGENT_TOKEN, url)

    def crawl_delay(self) -> float | None:
        if self.parser is None:
            return None
        delay = self.parser.crawl_delay(USER_AGENT_TOKEN)
        return float(delay) if delay is not None else None

    def to_dict(self) -> dict:
        return {
            "robots_url": self.robots_url,
            "status": self.status,
            "crawl_delay": self.crawl_delay(),
            "error": self.error,
        }


def parse_robots(text: str, robots_url: str) -> RobotsPolicy:
    """Tworzy politykę z treści pliku robots.txt (bez sieci – używane też w testach)."""
    parser = RobotFileParser(robots_url)
    parser.parse(text.splitlines())
    return RobotsPolicy(robots_url=robots_url, status=STATUS_OK, parser=parser)


def fetch_robots(url: str, user_agent: str, timeout: float = 10.0) -> RobotsPolicy:
    """Pobiera robots.txt dla witryny, do której należy `url`."""
    robots_url = robots_url_for(url)
    request = urllib.request.Request(robots_url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(512 * 1024)  # RFC 9309: limit co najmniej 500 KiB
            charset = response.headers.get_content_charset() or "utf-8"
            text = raw.decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        if 400 <= exc.code < 500:
            return RobotsPolicy(robots_url, STATUS_MISSING, error=f"HTTP {exc.code}")
        return RobotsPolicy(robots_url, STATUS_UNREACHABLE, error=f"HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        return RobotsPolicy(robots_url, STATUS_UNREACHABLE, error=str(reason))
    return parse_robots(text, robots_url)


class RobotsCache:
    """Pamięta robots.txt per witryna (schemat + host), żeby nie pobierać go wielokrotnie."""

    def __init__(self, user_agent: str, enabled: bool = True, timeout: float = 10.0):
        self.user_agent = user_agent
        self.enabled = enabled
        self.timeout = timeout
        self._cache: dict[str, RobotsPolicy] = {}

    def policy_for(self, url: str) -> RobotsPolicy:
        key = robots_url_for(url)
        if not self.enabled:
            return RobotsPolicy(key, STATUS_IGNORED)
        if key not in self._cache:
            self._cache[key] = fetch_robots(url, self.user_agent, self.timeout)
        return self._cache[key]

    def can_fetch(self, url: str) -> bool:
        return self.policy_for(url).can_fetch(url)
