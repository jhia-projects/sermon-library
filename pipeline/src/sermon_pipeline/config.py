"""Per-church source configuration (pipeline/sources/<church-id>.toml)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[2]
SOURCES_DIR = PIPELINE_DIR / "sources"


@dataclass(frozen=True)
class SourceConfig:
    church: dict[str, str]
    # Primary feed. A church with several feeds (St Helen's: Sunday + midweek) lists the rest in
    # rss_more_urls; every one is required (policy rule 2 applies per feed).
    rss_url: str | None = None
    rss_more_urls: tuple[str, ...] = ()
    # Item parser in rss.FEED_FORMATS ("generic" unless the church's feed needs its own).
    rss_format: str = "generic"
    # Required when rss_url is absent: why this church can only be scraped.
    rss_unavailable_reason: str | None = None
    scraper: str | None = None
    media_page_url: str | None = None
    series_pages: tuple[str, ...] = ()
    # The church's committed sermon archive (JSON lines, relative to pipeline/; see snapshot.py):
    # seeded by a one-off crawl. Scrapers that have one read it instead of re-crawling every build.
    snapshot: str | None = None
    # Keep only sermons dated on a Sunday (drops midweek talks from a mixed archive).
    sunday_only: bool = False
    min_book_share: float = 0.8
    exclude_series: tuple[str, ...] = ()
    # Case-insensitive substrings of series names to exclude (seasonal: "christmas", "carol").
    exclude_patterns: tuple[str, ...] = ()
    # One sermon preached at several services on the same day (St Helen's: 9.30am + 11.15am,
    # 4pm + 6pm) appears once per service. When true, a series keeps one copy per morning and one
    # per evening service each date: the earliest service.
    one_per_service_half: bool = False
    # Weekend-away / conference series (case-insensitive substrings of the name, e.g. "weekend").
    # Such a series, or any series with at least half its sermons on one date, is kept only if
    # its in-book passages work forward through the book; otherwise it is topical and skipped.
    event_patterns: tuple[str, ...] = ()
    # Month-day strings ("01-01") a source uses when it knows only the year. A series with two or
    # more sermons on one such date is skipped: its dates and order can't be trusted.
    placeholder_dates: tuple[str, ...] = ()
    series_aliases: dict[str, str] = field(default_factory=dict)
    speaker_aliases: dict[str, str] = field(default_factory=dict)

    @property
    def snapshot_path(self) -> Path | None:
        return PIPELINE_DIR / self.snapshot if self.snapshot else None

    @property
    def church_id(self) -> str:
        return self.church["id"]

    @property
    def rss_urls(self) -> tuple[str, ...]:
        return (self.rss_url, *self.rss_more_urls) if self.rss_url else ()

    @classmethod
    def from_dict(cls, d: dict) -> SourceConfig:
        from .policy import check_source_config  # local import: policy depends on this module

        rss = d.get("rss", {})
        scrape = d.get("scrape", {})
        series = d.get("series", {})
        aliases = d.get("aliases", {})
        if "url" in rss and "urls" in rss:
            raise ValueError(f"{d['church'].get('id')}: set [rss].url or [rss].urls, not both")
        urls = list(rss.get("urls", ())) or ([rss["url"]] if "url" in rss else [])
        cfg = cls(
            church=dict(d["church"]),
            rss_url=urls[0] if urls else None,
            rss_more_urls=tuple(urls[1:]),
            rss_format=rss.get("format", "generic"),
            rss_unavailable_reason=rss.get("unavailable_reason"),
            scraper=scrape.get("scraper"),
            media_page_url=scrape.get("media_page_url"),
            series_pages=tuple(scrape.get("series_pages", ())),
            snapshot=scrape.get("snapshot"),
            sunday_only=bool(scrape.get("sunday_only", False)),
            min_book_share=float(series.get("min_book_share", 0.8)),
            exclude_series=tuple(series.get("exclude", ())),
            exclude_patterns=tuple(series.get("exclude_patterns", ())),
            one_per_service_half=bool(series.get("one_per_service_half", False)),
            event_patterns=tuple(series.get("event_patterns", ())),
            placeholder_dates=tuple(series.get("placeholder_dates", ())),
            series_aliases=dict(aliases.get("series", {})),
            speaker_aliases=dict(aliases.get("speaker", {})),
        )
        if not 0.8 <= cfg.min_book_share <= 1.0:
            raise ValueError(f"{cfg.church_id}: min_book_share must be between 0.8 and 1.0")
        check_source_config(cfg)
        return cfg


def load_source(path: Path) -> SourceConfig:
    with path.open("rb") as f:
        return SourceConfig.from_dict(tomllib.load(f))


def load_all_sources(directory: Path = SOURCES_DIR) -> list[SourceConfig]:
    return [load_source(p) for p in sorted(directory.glob("*.toml"))]
