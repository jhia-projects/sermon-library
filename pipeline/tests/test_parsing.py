from __future__ import annotations

from datetime import date

import pytest

from sermon_pipeline.normalize import parse_duration, parse_series_label, split_title_and_passage
from sermon_pipeline.rss import FeedError, parse_feed
from sermon_pipeline.scrapers.allsouls import parse_media_listing, parse_series_page
from sermon_pipeline.scripture import parse_reference

from .conftest import AS


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Jonah 1", ("Jonah", 1, None, 1, None)),
        ("Acts 12:19–24", ("Acts", 12, 19, 12, 24)),
        ("1 Thessalonians 4:15 – 5:11", ("1Thess", 4, 15, 5, 11)),
        ("Psalm 102", ("Ps", 102, None, 102, None)),
        ("Proverbs 14:26", ("Prov", 14, 26, 14, 26)),
        ("Daniel 1–2", ("Dan", 1, None, 2, None)),
        ("1 Kings 1:5-21", ("1Kgs", 1, 5, 1, 21)),
        ("Romans 6:1–14, 23", ("Rom", 6, 1, 6, 14)),
    ],
)
def test_parse_reference(text, expected):
    r = parse_reference(text)
    assert r is not None
    assert (r.book, r.start_chapter, r.start_verse, r.end_chapter, r.end_verse) == expected


@pytest.mark.parametrize("text", ["", "Good Friday", "Hezekiah 3:1", "Acts 12:24–19"])
def test_parse_reference_rejects(text):
    assert parse_reference(text) is None


def test_split_title_and_passage():
    assert split_title_and_passage("No Favourites (7) (Acts 12:19–24)") == ("No Favourites (7)", "Acts 12:19–24")
    assert split_title_and_passage("But I say to you.mp3 (Luke 18:9–14)") == ("But I say to you", "Luke 18:9–14")
    assert split_title_and_passage("Good Friday Meditation Service") == ("Good Friday Meditation Service", None)


@pytest.mark.parametrize(
    "desc, expected",
    [
        ("Series: Jonah", ("Jonah", True)),
        ("Series: But I say to you...'", ("But I say to you", True)),
        ("One Generation From Extinction: Love in Crisis", ("One Generation From Extinction", True)),
        ("One Generation From Extinction", ("One Generation From Extinction", False)),
        ("", (None, False)),
        (None, (None, False)),
    ],
)
def test_parse_series_label(desc, expected):
    assert parse_series_label(desc) == expected


def test_parse_duration():
    assert parse_duration("00:28:49") == 1729
    assert parse_duration("40:11") == 2411
    assert parse_duration("bogus") is None


def test_parse_all_souls_feed():
    items = parse_feed((AS / "rss.xml").read_text(encoding="utf-8"))
    assert len(items) == 104
    jonah = items[0]
    assert jonah.source_key == "371615"
    assert jonah.origin == "rss"
    assert jonah.title == "1. Jonah (1)"
    assert jonah.passage_text == "Jonah 1"
    assert jonah.series_name == "Jonah" and jonah.series_label_explicit
    assert jonah.speaker == "Simon Dickson"
    assert jonah.date == date(2026, 11, 15)
    assert jonah.duration_seconds == 1729
    assert jonah.audio_url.endswith(".mp3")
    assert jonah.image_url == "https://www.allsouls.org/Images/Content/1141/1629804.jpeg"


def test_feed_errors():
    with pytest.raises(FeedError):
        parse_feed("<html>not a feed</html>")
    with pytest.raises(FeedError):
        parse_feed("<rss><channel>")


def test_parse_media_listing():
    rows = parse_media_listing((AS / "allmedia.html").read_text(encoding="utf-8"), "https://www.allsouls.org/Media/AllMedia.aspx")
    assert len(rows) == 10
    jonah = next(r for r in rows if r.source_key == "371615")
    assert jonah.origin == "scrape"
    assert jonah.title == "Jonah (1)"
    assert jonah.series_url == "https://www.allsouls.org/Groups/472096/Jonah.aspx"
    assert jonah.youtube_id == "KdHSvINr5-I"
    assert jonah.date == date(2026, 11, 15)
    assert jonah.passage_text == "Jonah 1"  # first reference only (second is Mark 3:35-41)
    assert jonah.duration_seconds == 1729


def test_parse_series_page():
    url = "https://www.allsouls.org/Groups/468891/No_Favourites.aspx"
    items = parse_series_page((AS / "group_no_favourites.html").read_text(encoding="utf-8"), url)
    assert len(items) == 7
    assert all(i.series_url == url and i.origin == "scrape" for i in items)
    assert [i.passage_text for i in items][-1] == "Acts 9:32–43"
    assert items[0].date == date(2026, 10, 25)
    assert items[0].audio_url.startswith("https://www.allsouls.org/Media/PlayMedia.aspx?download=file&media_id=")


def test_parse_archive_listing_old_format():
    """Archive page 600 (1977): 'Reference:' singular, 'MP3 Audio' + '64Kbps', coded group links."""
    rows = parse_media_listing(
        (AS / "archive_page_600.html").read_text(encoding="utf-8"), "https://www.allsouls.org/Media/AllMedia.aspx"
    )
    assert len(rows) == 10
    r = next(r for r in rows if r.source_key == "218870")
    assert r.title == "When man hides from God"
    assert r.date.isoformat() == "1977-11-13"
    assert r.series_name == "Genesis" and r.series_label_explicit
    assert r.passage_text == "Genesis 3:8"
    assert r.audio_url == "https://www.allsouls.org/Media/PlayMedia.aspx?download=file&media_id=218870&file_id=232242"
    assert r.series_url == "https://www.allsouls.org/Groups/319032/ZA008_Genesis.aspx"
    assert next(r for r in rows if r.source_key == "218394").title == "Jesus went to the Cross for you"  # quotes stripped


def test_books_json_matches_schema_enum():
    import json

    from sermon_pipeline.scripture import BOOKS
    from sermon_pipeline.validate import load_schema

    assert [b["code"] for b in BOOKS] == load_schema()["$defs"]["bookCode"]["enum"]
    assert [b["order"] for b in BOOKS] == list(range(1, 67))


def test_parse_references_multiple():
    from sermon_pipeline.scripture import parse_references

    refs = parse_references("Psalm 22:1–21", "Psalm 22:1-21; Mark 15:16-32")
    assert [(r.book, r.display) for r in refs] == [("Ps", "Psalm 22:1–21"), ("Mark", "Mark 15:16-32")]
    assert [r.book for r in parse_references("Romans 1:1-7, 16")] == ["Rom"]  # bare "16" not guessed
    assert parse_references(None, "") == []


def test_listing_keeps_every_reference():
    rows = parse_media_listing((AS / "allmedia.html").read_text(encoding="utf-8"), "https://www.allsouls.org/Media/AllMedia.aspx")
    jonah = next(r for r in rows if r.source_key == "371615")
    assert jonah.passage_text == "Jonah 1"
    assert jonah.listed_references == "Jonah 1; Mark 3:35-41"
