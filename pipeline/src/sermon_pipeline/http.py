"""Polite HTTP: identifies itself, obeys robots.txt and Crawl-delay. Swappable for tests."""

from __future__ import annotations

import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from typing import Protocol
from urllib.parse import urlsplit

import certifi

USER_AGENT = "sermon-library-pipeline/0.1 (RSS-first sermon index)"
MIN_DELAY_SECONDS = 2.0
_SSL = ssl.create_default_context(cafile=certifi.where())


class Fetcher(Protocol):
    def get(self, url: str) -> str: ...

    def post(self, url: str, form: dict[str, str]) -> str: ...


class RobotsDisallowed(Exception):
    pass


class PoliteFetcher:
    def __init__(self, user_agent: str = USER_AGENT, timeout: float = 30.0) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last_hit: dict[str, float] = {}

    def get(self, url: str) -> str:
        return self._request(url, None)

    def post(self, url: str, form: dict[str, str]) -> str:
        """Form POST (ASP.NET postback pagination). Same robots/delay rules as GET."""
        return self._request(url, urllib.parse.urlencode(form).encode("utf-8"))

    def _request(self, url: str, body: bytes | None) -> str:
        parts = urlsplit(url)
        if parts.scheme != "https":
            raise ValueError(f"refusing non-https url: {url}")
        host = parts.netloc
        robots = self._robots_for(f"{parts.scheme}://{host}")
        if not robots.can_fetch(self.user_agent, url):
            raise RobotsDisallowed(url)
        delay = max(float(robots.crawl_delay(self.user_agent) or 0), MIN_DELAY_SECONDS)
        wait = self._last_hit.get(host, 0) + delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        headers = {"User-Agent": self.user_agent}
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=_SSL) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(charset, errors="replace")
        finally:
            self._last_hit[host] = time.monotonic()

    def _robots_for(self, origin: str) -> urllib.robotparser.RobotFileParser:
        if origin not in self._robots:
            rp = urllib.robotparser.RobotFileParser(f"{origin}/robots.txt")
            req = urllib.request.Request(rp.url, headers={"User-Agent": self.user_agent})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout, context=_SSL) as resp:
                    rp.parse(resp.read().decode("utf-8", errors="replace").splitlines())
            except urllib.error.HTTPError as e:
                # RFC 9309: 4xx = no rules (allowed); 5xx = assume full disallow.
                if 400 <= e.code < 500:
                    rp.parse([])
                else:
                    raise
            # Network/TLS errors propagate: never treat "couldn't read robots.txt" as permission.
            self._robots[origin] = rp
        return self._robots[origin]
