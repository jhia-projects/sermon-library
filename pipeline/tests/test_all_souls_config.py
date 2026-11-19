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


def test_ephesians_split_by_label_is_one_series(all_souls):
    """'A CHURCH FOR ALL' (Eph 1:1-3:13, 2018) and 'CHURCH FOR ALL' (Eph 3:14-6:24, 2019) are one series."""
    sermons = [
        _s(1, date(2018, 10, 14), "Ephesians 1:1-14", "A CHURCH FOR ALL"),
        _s(2, date(2018, 11, 11), "Ephesians 3:1-13", "A CHURCH FOR ALL"),
        _s(3, date(2019, 1, 13), "Ephesians 3:14-21", "CHURCH FOR ALL"),
        _s(4, date(2019, 3, 3), "Ephesians 6:10-24", "CHURCH FOR ALL"),
    ]
    titles, _ = _titles(all_souls, sermons)
    assert titles == {"CHURCH FOR ALL": 4}  # the source's own spelling


def test_occasion_and_guest_series_are_excluded(all_souls):
    """Each of these passed the book rules on the 100-page build but isn't a book study."""
    sermons = [
        _s(1, date(2021, 10, 10), "Luke 2:22-35", "Guest Service"),
        _s(2, date(2021, 10, 17), "Luke 12:13-21", "Guest Service"),
        _s(3, date(2021, 4, 25), "Ephesians 4:1-16", "The John Stott Centenary"),
        _s(4, date(2021, 4, 25), "Ephesians 3:10-21", "The John Stott Centenary"),
        _s(5, date(2022, 4, 3), "Luke 22:66-23:25", "Questions From the Cross"),
        _s(6, date(2022, 4, 10), "Luke 23:26-49", "Questions From the Cross"),
    ]
    titles, report = _titles(all_souls, sermons)
    assert titles == {}
    assert {report.skipped_series[k] for k in ("Guest Service", "The John Stott Centenary", "Questions From the Cross")} == {"excluded in config"}


def test_joshua_split_by_label_is_one_series(all_souls):
    """'Inheritors of the Promise' (Joshua 7-12, Jan-Feb 2014) sits between two runs of 'Inheriting the Promise'."""
    sermons = [
        _s(1, date(2013, 6, 23), "Joshua 1", "Inheriting the Promise"),
        _s(2, date(2013, 7, 21), "Joshua 5:13-6:27", "Inheriting the Promise"),
        _s(3, date(2014, 1, 12), "Joshua 7", "Inheritors of the Promise"),
        _s(4, date(2014, 2, 23), "Joshua 11-12", "Inheritors of the Promise"),
        _s(5, date(2014, 5, 18), "Joshua 13-14", "Inheriting the Promise"),
        _s(6, date(2014, 7, 6), "Joshua 24", "Inheriting the Promise"),
    ]
    titles, _ = _titles(all_souls, sermons)
    assert titles == {"Inheriting the Promise": 6}


def _pair(key, d, passages, series):
    return [_s(f"{key}{i}", d, p, series) for i, p in enumerate(passages)]


def test_lent_to_easter_series_excluded_except_matthews_passion(all_souls):
    """Owner decision 2026-11-17 on the 200-page build: keep 'Matthew's Passion' (Matthew 26-28), exclude the rest."""
    sermons = [
        _s(1, date(2014, 3, 16), "Matthew 26:1-16", "Matthew's Passion"),
        _s(2, date(2014, 3, 23), "Matthew 26:17-35", "Matthew's Passion"),
        _s(3, date(2018, 3, 18), "Luke 22:7-23", "THREE DAYS THAT CHANGED THE WORLD"),
        _s(4, date(2018, 3, 25), "Luke 23:32-49", "THREE DAYS THAT CHANGED THE WORLD"),
        _s(5, date(2017, 3, 12), "John 17:1-26", "Series from John's Gospel"),
        _s(6, date(2017, 3, 19), "John 18:1-14", "Series from John's Gospel"),
        _s(7, date(2017, 4, 2), "Luke 19:11-27", "Series from Luke's Gospel"),
        _s(8, date(2017, 4, 9), "Luke 19:28-48", "Series from Luke's Gospel"),
        _s(9, date(1995, 3, 30), "Luke 23:26-31", "At the End?"),
        _s(10, date(1995, 4, 6), "Luke 23:32-39", "At the End?"),
        _s(11, date(2016, 3, 13), "John 12:12-29", "The Glory of the Cross"),
        _s(12, date(2016, 3, 20), "John 12:30-49", "The Glory of the Cross"),
    ]
    titles, report = _titles(all_souls, sermons)
    assert titles == {"Matthew's Passion": 2}
    assert sum(v == "excluded in config" for v in report.skipped_series.values()) == 5


def test_evangelistic_and_occasion_series_excluded(all_souls):
    """Themed talks that happen to share a Gospel, often two on one day (200-page build)."""
    sermons = [
        *_pair("a", date(1992, 1, 26), ["Luke 22:14-23", "Luke 24:36-49"], "The Time of Your Life"),
        *_pair("b", date(1994, 10, 8), ["Luke 12:16-21", "Luke 5:17-26"], "Right at the Centre"),
        *_pair("c", date(1992, 1, 5), ["Matthew 4:1-11", "Matthew 9:35-38"], "A Fresh Start to the Year"),
        *_pair("d", date(2008, 6, 1), ["Matthew 6:25-34", "Matthew 5:21-48"], "Workplace Sunday (Advice from the Boss)"),
    ]
    titles, report = _titles(all_souls, sermons)
    assert titles == {}
    assert sum(v == "excluded in config" for v in report.skipped_series.values()) == 4
