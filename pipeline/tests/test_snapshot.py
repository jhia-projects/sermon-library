"""The committed sermon archive (snapshot.py): scraped data, read by the scraper, feed still wins."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date

from sermon_pipeline.build import collect
from sermon_pipeline.config import SOURCES_DIR, load_source
from sermon_pipeline.models import DATA_FIELDS, RawSermon
from sermon_pipeline.snapshot import from_row, read_snapshot, to_row, write_snapshot

from .conftest import FakeFetcher


def _old_sermon(key: str = "1", **kw) -> RawSermon:
    fields = dict(
        title="The Old Sermon",
        date=date(1985, 3, 3),
        speaker="John Stott",
        series_name="Romans",
        series_label_explicit=True,
        passage_text="Romans 1:1-7",
        listed_references="Romans 1:1-7",
        audio_url="https://www.allsouls.org/Media/PlayMedia.aspx?download=file&media_id=1&file_id=2",
        source_url="https://www.allsouls.org/Media/Play.aspx?media_id=1",
    )
    fields.update(kw)
    return RawSermon(source_key=key, origin="scrape", **fields)


def test_row_round_trip_keeps_every_field():
    s = _old_sermon(
        video_url="https://example.org/v.mp4", youtube_id="abc", duration_seconds=1740,
        image_url="https://example.org/i.png", series_url="https://www.allsouls.org/Groups/1/Romans.aspx",
        service_time="11am",
    )
    assert all(getattr(s, f) not in (None, "") for f in DATA_FIELDS)  # the test covers every field
    back = from_row(json.loads(json.dumps(to_row(s))))
    assert back.values() == s.values()
    assert back.origin == "scrape"  # the archive is backfill, never feed data


def test_write_keeps_listing_order_and_one_row_per_sermon(tmp_path):
    # Order matters: a tie between series spellings goes to the first sermon read.
    path = tmp_path / "sermons.jsonl"
    rows = [_old_sermon("9", title="Newest"), _old_sermon("3"), _old_sermon("9", title="dup", youtube_id="yt")]
    assert write_snapshot(path, rows) == 2
    got = read_snapshot(path)
    assert [s.source_key for s in got] == ["9", "3"]
    assert got[0].title == "Newest" and got[0].youtube_id == "yt"  # first wins; gaps filled from later rows
    write_snapshot(path, got)  # rewriting what was read changes nothing
    assert [to_row(s) for s in read_snapshot(path)] == [to_row(s) for s in got]


def test_build_reads_archive_and_feed_still_wins(all_souls, tmp_path):
    """The archive adds sermons the feed and page 1 lack, but never overrides a feed value."""
    feed_items, _ = collect(all_souls, FakeFetcher(), scrape=False)
    in_feed = feed_items[0]
    path = tmp_path / "sermons.jsonl"
    write_snapshot(path, [_old_sermon("1"), _old_sermon(in_feed.source_key, title="Archive's title")])
    cfg = replace(all_souls, snapshot=str(path))  # absolute path: PIPELINE_DIR / abs == abs

    sermons, report = collect(cfg, FakeFetcher())
    by_key = {s.source_key: s for s in sermons}
    assert by_key["1"].title == "The Old Sermon" and by_key["1"].origin == "scrape"
    assert by_key[in_feed.source_key].title == in_feed.title  # feed wins
    assert report.ignored_conflicts["title"] >= 1


def test_update_adds_new_sermons_at_the_top_and_keeps_old_ones(all_souls, tmp_path):
    path = tmp_path / "sermons.jsonl"
    write_snapshot(path, [_old_sermon("1")])
    cfg = replace(all_souls, snapshot=str(path))
    scraped: list[RawSermon] = []
    collect(cfg, FakeFetcher(), scraped_out=scraped)
    write_snapshot(path, scraped)
    keys = [s.source_key for s in read_snapshot(path)]
    assert "1" in keys and keys[0] != "1"  # page 1's sermons come first; the old one is kept
    assert len(keys) == len(set(keys)) > 1


def test_committed_all_souls_archive_loads():
    cfg = load_source(SOURCES_DIR / "all-souls-langham-place.toml")
    assert cfg.snapshot_path and cfg.snapshot_path.exists()
    sermons = read_snapshot(cfg.snapshot_path)
    assert len(sermons) > 6000
    assert len({s.source_key for s in sermons}) == len(sermons)
    assert all(s.audio_url is None or s.audio_url.startswith("https://") for s in sermons)


def test_only_opted_in_scrapers_rewrite_their_archive():
    """St Helen's filters what it reads (Sunday only) and keeps talks.jsonl via crawl-sthelens: a
    build must never rewrite it, or midweek talks would be lost from the archive."""
    from sermon_pipeline.scrapers import get_scraper

    assert get_scraper("allsouls").updates_snapshot is True
    assert get_scraper("sthelens").updates_snapshot is False


def test_build_report_lists_series_per_church(tmp_path, monkeypatch):
    """`build --report` is what the weekly PR diffs: one section per church, one line per series."""
    from sermon_pipeline import cli

    monkeypatch.setattr(cli, "PoliteFetcher", lambda *a, **kw: FakeFetcher())
    report = tmp_path / "series-report.txt"
    args = ["build", "--source", str(SOURCES_DIR / "all-souls-langham-place.toml"),
            "--report", str(report), "--out", str(tmp_path / "library.json")]
    assert cli.main(args) == 0
    lines = report.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "## all-souls-langham-place"
    assert any(line.startswith("+ ") for line in lines) and any(line.startswith("- ") for line in lines)
