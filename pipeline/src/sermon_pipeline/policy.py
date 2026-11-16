"""RSS-over-scraping policy. Every rule here is enforced, not advisory.

1. Config: a church must declare an RSS feed, or explicitly say why it has none
   (`[rss] unavailable_reason`). A scraper alone is never a valid configuration by default.
2. No silent fallback: if a feed is configured and fails (HTTP error, unparsable, empty) the
   church's build fails. We never quietly switch to scraping instead.
3. Feed discovery: if a scrape-only church's pages advertise an RSS/Atom feed, the build fails
   so someone switches the config to the feed.
4. Merge: RSS records always win. Scraped data may only
     - backfill: add sermons whose source_key is absent from the feed, and
     - enrich: fill fields the feed left empty on a sermon it does contain.
   A scraped value never replaces a feed value; disagreements are counted and reported.
5. Post-merge assertion: every feed sermon survives the merge with every feed value intact.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field, replace
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .config import SourceConfig
from .models import DATA_FIELDS, RawSermon, _has_value
from .normalize import series_key


class PolicyError(Exception):
    """A church's configuration or build breaks the RSS-first policy."""


# --- 1. config ------------------------------------------------------------------------------


def check_source_config(cfg: SourceConfig) -> None:
    cid = cfg.church.get("id", "<unknown>")
    if cfg.rss_url and cfg.rss_unavailable_reason:
        raise PolicyError(f"{cid}: set either [rss].url or [rss].unavailable_reason, not both")
    if not cfg.rss_url:
        if not (cfg.rss_unavailable_reason or "").strip():
            raise PolicyError(
                f"{cid}: no RSS feed configured. Add [rss].url (preferred) or, if the church "
                "really publishes no feed, [rss].unavailable_reason explaining what was checked."
            )
        if not cfg.scraper:
            raise PolicyError(f"{cid}: no RSS feed and no scraper; nothing to build from")
    elif not cfg.rss_url.startswith("https://"):
        raise PolicyError(f"{cid}: RSS url must be https: {cfg.rss_url}")


# --- 2. no silent fallback ------------------------------------------------------------------


def require_feed_items(cfg: SourceConfig, items: list[RawSermon]) -> None:
    if cfg.rss_url and not items:
        raise PolicyError(
            f"{cfg.church_id}: RSS feed {cfg.rss_url} returned no sermons. Refusing to fall back "
            "to scraping; fix the feed URL or parser."
        )


# --- 3. feed discovery ----------------------------------------------------------------------

_FEED_TYPES = {"application/rss+xml", "application/atom+xml", "application/feed+json"}
_FEED_HREF = re.compile(r"(?:^|/)(?:rss|atom|feed)(?:\.xml|\.rss|/)?(?:$|\?)|\.rss$|podcast\.xml$", re.I)


def find_feed_links(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    for link in soup.find_all("link", href=True):
        rel = {r.lower() for r in (link.get("rel") or [])}
        if "alternate" in rel and (link.get("type") or "").lower() in _FEED_TYPES:
            found.append(urljoin(page_url, link["href"]))
    for a in soup.find_all("a", href=True):
        href = a["href"].split("#", 1)[0]
        if _FEED_HREF.search(href):
            found.append(urljoin(page_url, href))
    return sorted(set(found), key=str.lower)


def check_page_for_feed(cfg: SourceConfig, html: str, page_url: str) -> None:
    """Called by scrapers on every page fetched. Only scrape-only churches can fail here."""
    if cfg.rss_url:
        return
    feeds = find_feed_links(html, page_url)
    if feeds:
        raise PolicyError(
            f"{cfg.church_id}: {page_url} advertises a feed ({', '.join(feeds)}) but the config "
            "is scrape-only. Set [rss].url and remove [rss].unavailable_reason."
        )


# --- 4. merge -------------------------------------------------------------------------------


@dataclass
class MergeReport:
    rss: int = 0
    scraped: int = 0
    backfilled: int = 0
    enriched: Counter[str] = field(default_factory=Counter)
    # Scraped values that disagreed with the feed and were discarded.
    ignored_conflicts: Counter[str] = field(default_factory=Counter)
    duplicate_rss_keys: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [
            f"rss={self.rss}",
            f"scraped={self.scraped}",
            f"backfilled={self.backfilled}",
            f"enriched={dict(self.enriched) or 0}",
        ]
        if self.ignored_conflicts:
            parts.append(f"ignored_scrape_conflicts={dict(self.ignored_conflicts)}")
        if self.duplicate_rss_keys:
            parts.append(f"duplicate_rss_keys={self.duplicate_rss_keys}")
        return " ".join(parts)


def merge_prefer_rss(rss: list[RawSermon], scraped: list[RawSermon]) -> tuple[list[RawSermon], MergeReport]:
    for s in rss:
        if s.origin != "rss":
            raise PolicyError(f"record {s.source_key} passed as RSS but has origin={s.origin}")
    for s in scraped:
        if s.origin != "scrape":
            raise PolicyError(f"record {s.source_key} passed as scraped but has origin={s.origin}")

    report = MergeReport(rss=len(rss), scraped=len(scraped))
    merged: dict[str, RawSermon] = {}
    for s in rss:
        if s.source_key in merged:
            report.duplicate_rss_keys.append(s.source_key)
            continue
        merged[s.source_key] = replace(s, provenance=dict(s.provenance))

    for sc in scraped:
        base = merged.get(sc.source_key)
        if base is None:
            merged[sc.source_key] = replace(sc, provenance=dict(sc.provenance))
            report.backfilled += 1
            continue
        if base.origin == "scrape":
            # Two scraped pages describing the same sermon: first one wins, fill gaps only.
            _fill_gaps(base, sc, None)
            continue
        _fill_gaps(base, sc, report)

    return list(merged.values()), report


def _fill_gaps(base: RawSermon, extra: RawSermon, report: MergeReport | None) -> None:
    for name in DATA_FIELDS:
        if name == "series_label_explicit":
            continue  # handled together with series_name below
        ours, theirs = getattr(base, name), getattr(extra, name)
        if not _has_value(theirs):
            continue
        if not _has_value(ours):
            setattr(base, name, theirs)
            base.provenance[name] = extra.origin
            if name == "series_name":
                base.series_label_explicit = extra.series_label_explicit
                if extra.series_label_explicit:
                    base.provenance["series_label_explicit"] = extra.origin
            if report is not None:
                report.enriched[name] += 1
        elif ours != theirs and report is not None and not _equivalent(name, ours, theirs):
            report.ignored_conflicts[name] += 1

    # Same series, but the scraped page labels it explicitly: upgrade confidence, keep feed name.
    if (
        base.series_name
        and extra.series_name
        and extra.series_label_explicit
        and not base.series_label_explicit
        and series_key(base.series_name) == series_key(extra.series_name)
    ):
        base.series_label_explicit = True
        base.provenance["series_label_explicit"] = extra.origin
        if report is not None:
            report.enriched["series_label_explicit"] += 1


def _equivalent(name: str, a: object, b: object) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        if name == "series_name":
            return series_key(a) == series_key(b)
        return re.sub(r"\W+", "", a).casefold() == re.sub(r"\W+", "", b).casefold()
    return False


# --- 5. post-merge assertion ----------------------------------------------------------------


def assert_rss_precedence(rss: list[RawSermon], merged: list[RawSermon]) -> None:
    by_key = {m.source_key: m for m in merged}
    seen: set[str] = set()
    for s in rss:
        if s.source_key in seen:
            continue
        seen.add(s.source_key)
        m = by_key.get(s.source_key)
        if m is None:
            raise PolicyError(f"RSS sermon {s.source_key} lost during merge")
        if m.origin != "rss":
            raise PolicyError(f"RSS sermon {s.source_key} replaced by a {m.origin} record")
        for name in DATA_FIELDS:
            v = getattr(s, name)
            if _has_value(v) and getattr(m, name) != v:
                raise PolicyError(f"RSS value {name}={v!r} for {s.source_key} overwritten by scraping")
            if _has_value(v) and m.provenance.get(name) != "rss":
                raise PolicyError(f"provenance of {name} for {s.source_key} is not rss")
