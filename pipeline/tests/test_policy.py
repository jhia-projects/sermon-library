"""The RSS-over-scraping policy. If one of these fails, do not 'fix' the test — fix the code."""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from sermon_pipeline.build import collect
from sermon_pipeline.config import SourceConfig, load_all_sources
from sermon_pipeline.models import RawSermon
from sermon_pipeline.policy import (
    PolicyError,
    assert_rss_precedence,
    check_source_config,
    find_feed_links,
    merge_prefer_rss,
)

from .conftest import FakeFetcher

CHURCH = {"id": "test-church", "name": "Test", "websiteUrl": "https://example.com"}


# --- 1. config ------------------------------------------------------------------------------


def test_every_committed_source_passes_policy():
    for cfg in load_all_sources():
        check_source_config(cfg)


def test_scrape_only_config_without_reason_is_rejected():
    with pytest.raises(PolicyError, match="no RSS feed configured"):
        SourceConfig.from_dict({"church": CHURCH, "scrape": {"scraper": "allsouls"}})


def test_scrape_only_config_with_reason_is_allowed():
    cfg = SourceConfig.from_dict(
        {
            "church": CHURCH,
            "rss": {"unavailable_reason": "Checked site, podcast apps and page <link> tags 2026-11-16."},
            "scrape": {"scraper": "allsouls"},
        }
    )
    assert cfg.rss_url is None


def test_rss_url_and_unavailable_reason_together_is_rejected():
    with pytest.raises(PolicyError, match="not both"):
        SourceConfig.from_dict(
            {"church": CHURCH, "rss": {"url": "https://example.com/rss.xml", "unavailable_reason": "x"}}
        )


def test_http_rss_rejected():
    with pytest.raises(PolicyError, match="https"):
        SourceConfig.from_dict({"church": CHURCH, "rss": {"url": "http://example.com/rss.xml"}})


# --- 2. no silent fallback ------------------------------------------------------------------


def test_feed_failure_fails_the_build_and_never_scrapes(all_souls):
    f = FakeFetcher(fail={all_souls.rss_url})
    with pytest.raises(OSError):
        collect(all_souls, f)
    assert f.calls == [all_souls.rss_url], "scraper must not run when the feed fails"


def test_empty_feed_fails_the_build_and_never_scrapes(all_souls):
    empty = '<?xml version="1.0"?><rss version="2.0"><channel><title>x</title></channel></rss>'
    f = FakeFetcher({all_souls.rss_url: empty})
    with pytest.raises(PolicyError, match="Refusing to fall back"):
        collect(all_souls, f)
    assert f.calls == [all_souls.rss_url]


def test_feed_is_fetched_before_any_scraping(all_souls, fetcher):
    collect(all_souls, fetcher)
    assert fetcher.calls[0] == all_souls.rss_url
    assert len(fetcher.calls) > 1  # scraper did run afterwards


def test_no_scrape_flag_fetches_only_the_feed(all_souls, fetcher):
    collect(all_souls, fetcher, scrape=False)
    assert fetcher.calls == [all_souls.rss_url]


# --- 3. feed discovery ----------------------------------------------------------------------


def test_feed_links_found_on_all_souls_media_page(fetcher):
    html = fetcher.get("https://www.allsouls.org/Media/AllMedia.aspx")
    feeds = find_feed_links(html, "https://www.allsouls.org/Media/AllMedia.aspx")
    assert "https://www.allsouls.org/Media/rss.xml" in feeds


def test_link_rel_alternate_is_detected():
    html = '<head><link rel="alternate" type="application/rss+xml" href="/podcast"></head>'
    assert find_feed_links(html, "https://example.com/") == ["https://example.com/podcast"]


def test_scrape_only_church_whose_pages_advertise_a_feed_fails(all_souls):
    scrape_only = dataclasses.replace(all_souls, rss_url=None, rss_unavailable_reason="pretend")
    with pytest.raises(PolicyError, match="advertises a feed"):
        collect(scrape_only, FakeFetcher())


# --- 4/5. merge -----------------------------------------------------------------------------


def _rss(key: str, **kw) -> RawSermon:
    return RawSermon(source_key=key, origin="rss", **kw)


def _scr(key: str, **kw) -> RawSermon:
    return RawSermon(source_key=key, origin="scrape", **kw)


def test_scraped_values_never_override_rss():
    rss = [_rss("1", title="Feed Title", audio_url="https://feed/a.mp3", date=date(2026, 1, 1))]
    scraped = [_scr("1", title="Scraped Title", audio_url="https://site/a.mp3", date=date(2026, 1, 2))]
    merged, report = merge_prefer_rss(rss, scraped)
    (m,) = merged
    assert (m.title, m.audio_url, m.date) == ("Feed Title", "https://feed/a.mp3", date(2026, 1, 1))
    assert report.ignored_conflicts == {"title": 1, "audio_url": 1, "date": 1}
    assert_rss_precedence(rss, merged)


def test_scrape_enriches_only_empty_fields_and_records_provenance():
    rss = [_rss("1", title="T", youtube_id=None)]
    scraped = [_scr("1", title="Other", youtube_id="abcdefghijk", series_url="https://site/series")]
    (m,), report = merge_prefer_rss(rss, scraped)
    assert m.origin == "rss"
    assert m.youtube_id == "abcdefghijk"
    assert m.provenance == {"title": "rss", "youtube_id": "scrape", "series_url": "scrape"}
    assert report.enriched == {"youtube_id": 1, "series_url": 1}


def test_scrape_backfills_sermons_missing_from_feed():
    rss = [_rss("2", title="Part 2")]
    scraped = [_scr("1", title="Part 1"), _scr("2", title="ignored")]
    merged, report = merge_prefer_rss(rss, scraped)
    assert {m.source_key: m.origin for m in merged} == {"2": "rss", "1": "scrape"}
    assert report.backfilled == 1


def test_bare_feed_label_upgraded_by_explicit_scrape_label_but_name_kept():
    rss = [_rss("1", series_name="no favourites", series_label_explicit=False)]
    scraped = [_scr("1", series_name="No Favourites", series_label_explicit=True)]
    (m,), _ = merge_prefer_rss(rss, scraped)
    assert m.series_name == "no favourites"
    assert m.series_label_explicit is True


def test_mislabelled_origin_is_rejected():
    with pytest.raises(PolicyError, match="origin"):
        merge_prefer_rss([_scr("1")], [])
    with pytest.raises(PolicyError, match="origin"):
        merge_prefer_rss([], [_rss("1")])


def test_precedence_assertion_catches_overwrite():
    rss = [_rss("1", title="Feed")]
    tampered = [_rss("1", title="Scraped")]
    with pytest.raises(PolicyError, match="overwritten"):
        assert_rss_precedence(rss, tampered)


def test_precedence_assertion_catches_replacement():
    rss = [_rss("1", title="Feed")]
    with pytest.raises(PolicyError, match="replaced"):
        assert_rss_precedence(rss, [_scr("1", title="Feed")])


def test_real_fixtures_rss_wins_every_conflict(all_souls, fetcher):
    merged, report = collect(all_souls, fetcher)  # collect() runs assert_rss_precedence itself
    by_key = {m.source_key: m for m in merged}
    jonah = by_key["371615"]
    assert jonah.title == "1. Jonah (1)"  # feed title, not the page's "Jonah (1)"
    assert jonah.audio_url.startswith("https://s3.")  # feed MP3, not the site download link
    assert jonah.youtube_id == "KdHSvINr5-I" and jonah.provenance["youtube_id"] == "scrape"
    assert report.ignored_conflicts["audio_url"] > 0
