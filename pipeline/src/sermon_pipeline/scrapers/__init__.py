"""Scrapers are BACKFILL ONLY. See policy.py for what they may and may not contribute."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from ..config import SourceConfig
from ..http import Fetcher
from ..models import RawSermon
from ..policy import check_page_for_feed


class Scraper:
    name: ClassVar[str]
    # True when everything run() returns may be written back as the church's archive
    # (`build --update-snapshot`, snapshot.py). False for scrapers that filter what they read
    # (St Helen's drops midweek talks) or keep their archive another way (crawl-sthelens).
    updates_snapshot: ClassVar[bool] = False

    def __init__(
        self,
        cfg: SourceConfig,
        fetcher: Fetcher,
        *,
        archive_pages: int = 0,
        rss_items: Sequence[RawSermon] = (),
    ) -> None:
        self.cfg = cfg
        self.fetcher = fetcher
        # The church's feed items, read-only. A scraper may use them to decide which pages to
        # fetch; it never changes them (the merge in policy.py decides what scraped data may add).
        self.rss_items = tuple(rss_items)
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
    from .sthelens import StHelensScraper

    registry: dict[str, type[Scraper]] = {AllSoulsScraper.name: AllSoulsScraper, StHelensScraper.name: StHelensScraper}
    try:
        return registry[name]
    except KeyError:
        raise KeyError(f"unknown scraper {name!r}; known: {sorted(registry)}") from None
