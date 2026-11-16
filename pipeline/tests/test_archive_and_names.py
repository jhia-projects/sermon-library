from __future__ import annotations

from sermon_pipeline.build import collect
from sermon_pipeline.names import find_similar, review_library, why_similar
from sermon_pipeline.scrapers.allsouls import AllSoulsScraper

from .conftest import ALL_SOULS_PAGES, AS, FakeFetcher

MEDIA = "https://www.allsouls.org/Media/AllMedia.aspx"


def test_archive_not_crawled_by_default(all_souls, fetcher):
    collect(all_souls, fetcher)
    assert fetcher.posts == []


def test_archive_crawl_posts_page_numbers_and_is_backfill_only(all_souls):
    f = FakeFetcher({**ALL_SOULS_PAGES, f"{MEDIA}#page=2": AS / "archive_page_600.html"})
    scraper = AllSoulsScraper(all_souls, f, archive_pages=2)
    rows = scraper.run()
    pages = [form["ctl00$ctl00$cphBody$cphSharedContents$hidden_page"] for _, form in f.posts]
    assert pages == ["2", "3"]  # page 3 came back empty -> stopped
    assert any(r.source_key == "218870" and r.origin == "scrape" for r in rows)
    assert all("searchSite" not in k for _, form in f.posts for k in form)

    merged, report = collect(all_souls, FakeFetcher({**ALL_SOULS_PAGES, f"{MEDIA}#page=2": AS / "archive_page_600.html"}),
                             archive_pages=1)
    assert report.backfilled >= 10  # 1977 sermons are absent from the feed


def test_name_similarity():
    assert why_similar("Ollie Lansdown", "Ollie Lansdowne") == "edit distance 1"
    assert why_similar("Revd Dr John Stott", "John Stott")
    assert why_similar("John Stott", "John R W Stott") == "same first and last name"
    assert why_similar("Hugh Palmer", "Rico Tice") is None
    assert why_similar("Jonah", "John") is None


def test_review_library_respects_reviewed_pairs():
    lib = {
        "speakers": [{"id": "a", "name": "Ollie Lansdown"}, {"id": "b", "name": "Ollie Lansdowne"}],
        "series": [],
    }
    assert [(p.a, p.b) for p in review_library(lib, reviewed=set())] == [("Ollie Lansdown", "Ollie Lansdowne")]
    assert review_library(lib, reviewed={("speaker", frozenset({"Ollie Lansdown", "Ollie Lansdowne"}))}) == []


def test_series_names_compared_within_book_only():
    assert find_similar("series", ["Jonah", "John"]) == []
