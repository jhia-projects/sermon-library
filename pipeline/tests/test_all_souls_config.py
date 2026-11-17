"""Pins the All Souls config decisions made after the 50-page archive build (2026-11-16).

Dates, labels and passages are the real ones from the site; source keys are made up.
"""
from __future__ import annotations

from datetime import date

from sermon_pipeline.build import build_church
from sermon_pipeline.models import RawSermon

TODAY = date(2026, 11, 16)


def _s(key, d, passage, series):
    return RawSermon(
        source_key=str(key), origin="scrape", title=f"Talk {key}", date=d, speaker="A Preacher",
        series_name=series, series_label_explicit=True, passage_text=passage,
        audio_url=f"https://example.com/{key}.mp3",
    )


def _titles(cfg, sermons):
    church, report = build_church(cfg, sermons, TODAY)
    return {s["title"]: len(s["sermons"]) for s in church["series"]}, report


def test_easter_series_is_excluded(all_souls):
    """'Easter' 2022: two Luke 24 sermons passed every book rule but is a seasonal series."""
    sermons = [_s(1, date(2022, 4, 10), "Luke 24:13-35", "Easter"), _s(2, date(2022, 4, 17), "Luke 24:36-53", "Easter")]
    titles, report = _titles(all_souls, sermons)
    assert titles == {}
    assert report.skipped_series["Easter"] == "excluded in config"


def test_genesis_flood_typo_is_one_series(all_souls):
    """'Moderns Lessons…' (3 sermons) and 'Modern Lessons…' (1) were split by a typo in the source."""
    label = "Modern Lessons From an Ancient Flood"
    sermons = [
        _s(1, date(2024, 10, 27), "Genesis 6:1-8", label),
        _s(2, date(2024, 11, 3), "Genesis 6:9-7:24", "Moderns Lessons From an Ancient Flood"),
        _s(3, date(2024, 11, 10), "Genesis 8", "Moderns Lessons From an Ancient Flood"),
        _s(4, date(2024, 11, 17), "Genesis 9", "Moderns Lessons From an Ancient Flood"),
    ]
    titles, _ = _titles(all_souls, sermons)
    assert titles == {label: 4}


def test_romans_label_variants_are_one_series(all_souls):
    """2023: four 'Romans 5: The Truly Free Life' rows (one with no reference) and one
    'Romans: The Truly Free Life' row. Split, they failed 80% (3/4) and 'single sermon'."""
    sermons = [
        _s(1, date(2023, 9, 3), "Romans 5:1-11", "Romans 5: The Truly Free Life"),
        _s(2, date(2023, 9, 10), "Romans 5:12-21", "Romans 5: The Truly Free Life"),
        _s(3, date(2023, 9, 17), None, "Romans 5: The Truly Free Life"),
        _s(4, date(2023, 9, 24), "Romans 6:1-14", "Romans 5: The Truly Free Life"),
        _s(5, date(2023, 10, 1), "Romans 6:15-23", "Romans: The Truly Free Life"),
    ]
    titles, _ = _titles(all_souls, sermons)
    assert titles == {"Romans: The Truly Free Life": 5}


def test_matthew_4_label_joins_matthew(all_souls):
    """2023: rows labelled 'Matthew 4' and 'Matthew' all link to the site's 'Matthew' series page."""
    sermons = [
        _s(1, date(2023, 9, 3), "Matthew 4:1-11", "Matthew 4"),
        _s(2, date(2023, 9, 10), "Matthew 4:12-17", "Matthew 4"),
        _s(3, date(2023, 9, 17), "Matthew 4:18-22", "Matthew 4"),
        _s(4, date(2023, 9, 24), "Matthew 4:23-5:16", "Matthew 4"),
        _s(5, date(2023, 10, 1), "Matthew 5:17-20", "Matthew"),
    ]
    titles, _ = _titles(all_souls, sermons)
    assert titles == {"Matthew": 5}
