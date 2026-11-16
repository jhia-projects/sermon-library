"""Per-church source configuration (pipeline/sources/<church-id>.toml)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

SOURCES_DIR = Path(__file__).resolve().parents[2] / "sources"


@dataclass(frozen=True)
class SourceConfig:
    church: dict[str, str]
    rss_url: str | None = None
    # Required when rss_url is absent: why this church can only be scraped.
    rss_unavailable_reason: str | None = None
    scraper: str | None = None
    media_page_url: str | None = None
    series_pages: tuple[str, ...] = ()
    min_book_share: float = 0.8
    exclude_series: tuple[str, ...] = ()
    # Case-insensitive substrings of series names to exclude (seasonal: "christmas", "carol").
    exclude_patterns: tuple[str, ...] = ()
    series_aliases: dict[str, str] = field(default_factory=dict)
    speaker_aliases: dict[str, str] = field(default_factory=dict)

    @property
    def church_id(self) -> str:
        return self.church["id"]

    @classmethod
    def from_dict(cls, d: dict) -> SourceConfig:
        from .policy import check_source_config  # local import: policy depends on this module

        rss = d.get("rss", {})
        scrape = d.get("scrape", {})
        series = d.get("series", {})
        aliases = d.get("aliases", {})
        cfg = cls(
            church=dict(d["church"]),
            rss_url=rss.get("url"),
            rss_unavailable_reason=rss.get("unavailable_reason"),
            scraper=scrape.get("scraper"),
            media_page_url=scrape.get("media_page_url"),
            series_pages=tuple(scrape.get("series_pages", ())),
            min_book_share=float(series.get("min_book_share", 0.8)),
            exclude_series=tuple(series.get("exclude", ())),
            exclude_patterns=tuple(series.get("exclude_patterns", ())),
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
