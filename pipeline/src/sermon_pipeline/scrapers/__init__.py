"""Scrapers are BACKFILL ONLY. See policy.py for what they may and may not contribute."""

from __future__ import annotations

from typing import ClassVar

from ..config import SourceConfig
from ..http import Fetcher
from ..models import RawSermon
from ..policy import check_page_for_feed


class Scraper:
    name: ClassVar[str]

    def __init__(self, cfg: SourceConfig, fetcher: Fetcher, *, archive_pages: int = 0) -> None:
        self.cfg = cfg
        self.fetcher = fetcher
        # How many archive listing pages beyond the first to crawl (0 = none). Scrapers without
        # an archive ignore it.
        self.archive_pages = archive_pages
        self.pages_fetched = 0

    def fetch_page(self, url: str) -> str:
        """All scraper fetches go through here so the feed-discovery check can't be skipped."""
        html = self.fetcher.get(url)
        self.pages_fetched += 1
        check_page_for_feed(self.cfg, html, url)
        return html

    def post_page(self, url: str, form: dict[str, str]) -> str:
        html = self.fetcher.post(url, form)
        self.pages_fetched += 1
        check_page_for_feed(self.cfg, html, url)
        return html

    def run(self) -> list[RawSermon]:
        raise NotImplementedError


def get_scraper(name: str) -> type[Scraper]:
    from .allsouls import AllSoulsScraper

    registry: dict[str, type[Scraper]] = {AllSoulsScraper.name: AllSoulsScraper}
    try:
        return registry[name]
    except KeyError:
        raise KeyError(f"unknown scraper {name!r}; known: {sorted(registry)}") from None
