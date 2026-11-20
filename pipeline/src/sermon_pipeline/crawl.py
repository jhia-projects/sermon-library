"""Disk-cached, resumable crawling on top of a Fetcher.

Every successful fetch is written to the cache before it is returned, so a URL is fetched at most
once across runs: an interrupted crawl resumes by re-running the same command. Permanent HTTP
errors (4xx) are cached too so they aren't retried; 5xx and network errors are not cached and
are retried on the next run.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.error
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from .http import Fetcher, RobotsDisallowed

log = logging.getLogger(__name__)


class CachedCrawler:
    def __init__(
        self,
        fetcher: Fetcher,
        cache_dir: Path,
        *,
        forbidden: Callable[[str], bool] = lambda url: False,
        allowed: Callable[[str], bool] | None = None,
    ) -> None:
        self.fetcher = fetcher
        self.cache_dir = cache_dir
        self.forbidden = forbidden  # hard per-site guard, checked before robots.txt
        self.allowed = allowed  # robots.txt verdict, checked before any network request
        self.fetched = 0  # network requests made by this run
        self.cache_hits = 0
        cache_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, url: str) -> Path:
        parts = urlsplit(url)
        stem = re.sub(r"[^A-Za-z0-9]+", "_", f"{parts.netloc}{parts.path}").strip("_")[:120]
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        return self.cache_dir / f"{stem}.{digest}"

    def cached(self, url: str) -> bool:
        p = self.path_for(url)
        return p.with_suffix(p.suffix + ".body").exists() or p.with_suffix(p.suffix + ".error").exists()

    def get(self, url: str) -> str | None:
        """Page body, from cache if present. None for a cached or new permanent (4xx) error."""
        if self.forbidden(url):
            raise RobotsDisallowed(f"refusing forbidden path: {url}")
        base = self.path_for(url)
        body_p = base.with_suffix(base.suffix + ".body")
        err_p = base.with_suffix(base.suffix + ".error")
        if body_p.exists():
            self.cache_hits += 1
            return body_p.read_text(encoding="utf-8")
        if err_p.exists():
            self.cache_hits += 1
            return None
        if self.allowed is not None and not self.allowed(url):
            raise RobotsDisallowed(url)
        self.fetched += 1
        try:
            body = self.fetcher.get(url)
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                _atomic_write(err_p, json.dumps({"url": url, "status": e.code}))
                log.warning("HTTP %s %s (cached; won't retry)", e.code, url)
                return None
            raise
        _atomic_write(body_p, body)
        return body


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
