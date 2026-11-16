from __future__ import annotations

import copy
import dataclasses
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sermon_pipeline import policy
from sermon_pipeline.build import build_church, build_library, collect
from sermon_pipeline.models import RawSermon
from sermon_pipeline.validate import validate_library

TODAY = date(2026, 11, 16)
EXAMPLE = Path(__file__).resolve().parents[2] / "schema" / "library.example.json"


def _build(cfg, fetcher):
    sermons, _ = collect(cfg, fetcher)
    church, report = build_church(cfg, sermons, TODAY)
    return build_library([church], datetime(2026, 11, 16, tzinfo=timezone.utc)), report


def test_all_souls_fixture_library_is_valid(all_souls, fetcher):
    lib, _ = _build(all_souls, fetcher)
    assert validate_library(lib) == []


def test_all_souls_series_selection(all_souls, fetcher):
    lib, report = _build(all_souls, fetcher)
    by_title = {s["title"]: s for s in lib["series"]}
    assert by_title["No Favourites"]["book"] == "Acts"
    assert len(by_title["No Favourites"]["sermons"]) == 7  # "No Favorites" spelling merged
    assert by_title["Jonah"]["isComplete"] is False  # in progress, single explicit sermon allowed
    # In the fixtures (feed + page 1 only) the Mark series has too many Daniel/Psalm interludes
    # for the 80% rule; with archive rows listing the Mark references it passes (tested below).
    assert "The King Who Chose to Die" not in by_title
    assert any(k.startswith("The King Who Chose to Die") and "not one book" in v
               for k, v in report.skipped_series.items())
    assert "World Mission Sunday" not in by_title  # excluded by name
    assert "Christmas Cheer" not in by_title  # excluded by pattern
    assert "Finding Truth" not in by_title  # topical, many books
    assert "Palm Sunday" not in by_title  # one-off
    for se in lib["series"]:
        in_book = sum(m.get("passage", {}).get("book") == se["book"] for m in se["sermons"])
        assert in_book >= 0.8 * len(se["sermons"])


def test_speaker_alias_and_global_speakers(all_souls, fetcher):
    lib, _ = _build(all_souls, fetcher)
    names = {sp["name"] for sp in lib["speakers"]}
    assert "Ollie Lansdown" not in names
    assert all(set(sp) <= {"id", "name", "photoUrl"} for sp in lib["speakers"])


def test_ids_are_stable_source_based(all_souls, fetcher):
    lib, _ = _build(all_souls, fetcher)
    jonah = next(s for s in lib["series"] if s["title"] == "Jonah")
    assert jonah["id"] == "all-souls-langham-place-jonah-2026-jonah"
    assert jonah["sermons"][0]["id"] == "all-souls-langham-place-371615"


def _s(key, d, passage, series="Romans", speaker="A Preacher"):
    return RawSermon(
        source_key=str(key), origin="rss", title=f"Talk {key}", date=d, speaker=speaker,
        series_name=series, series_label_explicit=True, passage_text=passage,
        audio_url=f"https://example.com/{key}.mp3",
    )


def _series(all_souls, sermons):
    church, report = build_church(all_souls, sermons, TODAY)
    return church["series"], report


def test_look_forward_one_year_splits_reused_names(all_souls):
    sermons = [
        _s(1, date(1985, 1, 6), "Romans 1:1-17"),
        _s(2, date(1985, 11, 3), "Romans 1:18-32"),  # 301 days later: same series
        _s(3, date(2012, 1, 8), "Romans 1:1-7"),  # decades later: a new series
        _s(4, date(2012, 1, 15), "Romans 1:8-17"),
    ]
    series, _ = _series(all_souls, sermons)
    assert sorted(s["id"] for s in series) == [
        "all-souls-langham-place-rom-1985-romans",
        "all-souls-langham-place-rom-2012-romans",
    ]
    gap = [_s(1, date(1990, 1, 7), "Romans 1"), _s(2, date(1991, 1, 13), "Romans 2")]  # 371 days
    series, report = _series(all_souls, gap)
    assert series == []  # two single-sermon runs
    assert sum("single sermon" in v for v in report.skipped_series.values()) == 2


def test_series_longer_than_three_years_is_skipped(all_souls):
    days = [date(2000, 1, 2), date(2000, 12, 3), date(2001, 11, 4), date(2002, 10, 6), date(2003, 3, 2)]
    series, report = _series(all_souls, [_s(i, d, f"Romans {i + 1}") for i, d in enumerate(days)])
    assert series == []
    assert any("spans 3.2 years" in v for v in report.skipped_series.values())


def test_sermon_counts_if_any_reference_is_in_the_book(all_souls):
    """'This Is the Royal Rescue': feed prints Psalm 22:1-21, the site lists Psalm 22 and Mark 15:16-32."""
    feed = [
        _s(1, date(2026, 3, 15), "Mark 15:1–15", series="The King Who Chose to Die"),
        _s(2, date(2026, 3, 22), "Psalm 22:1–21", series="The King Who Chose to Die"),
        _s(3, date(2026, 3, 29), "Mark 15:33–47", series="The King Who Chose to Die"),
    ]
    strict = dataclasses.replace(all_souls, min_book_share=1.0)
    series, report = _series(strict, feed)
    assert series == []  # feed alone, 100% rule: Psalm 22 is off-book

    site = RawSermon(source_key="2", origin="scrape", listed_references="Psalm 22:1-21; Mark 15:16-32")
    merged, merge = policy.merge_prefer_rss(feed, [site])
    assert merge.enriched["listed_references"] == 1
    assert next(m for m in merged if m.source_key == "2").passage_text == "Psalm 22:1–21"  # feed value kept
    series, _ = _series(strict, merged)
    (se,) = series
    assert se["book"] == "Mark"
    assert [m["passage"]["display"] for m in se["sermons"]] == ["Mark 15:1–15", "Mark 15:16-32", "Mark 15:33–47"]
    assert validate_library(build_library([build_church(all_souls, merged, TODAY)[0]], datetime(2026, 11, 16, tzinfo=timezone.utc))) == []


def _romans_run(passages):
    return [_s(i, date(2020, 1, 5) + timedelta(weeks=i), p) for i, p in enumerate(passages, 1)]


def test_interlude_and_missing_reference_stay_in_series_at_80_percent(all_souls):
    # 8/10 = 80% in Romans: the Psalm interlude and the missing reference neither drop nor split it.
    passages = ["Romans 1", "Romans 2", "Romans 3", "Psalm 32", "Romans 4",
                "Romans 5", None, "Romans 6", "Romans 7", "Romans 8"]
    run = _romans_run(passages)
    (se,), report = _series(all_souls, run)
    assert se["book"] == "Rom"
    assert len(se["sermons"]) == 10
    assert se["sermons"][3]["passage"]["book"] == "Ps"
    assert "passage" not in se["sermons"][6]  # never guessed
    assert report.kept_off_book == {"Romans (2020-01-12)": 2}
    lib = build_library([build_church(all_souls, run, TODAY)[0]], datetime(2026, 11, 16, tzinfo=timezone.utc))
    assert validate_library(lib) == []


def test_below_80_percent_is_skipped(all_souls):
    run = _romans_run(["Romans 1", "Psalm 32", "Romans 2", "Psalm 51"])  # 50%
    series, report = _series(all_souls, run)
    assert series == []
    assert any("not one book: 50% Rom" in v for v in report.skipped_series.values())


def test_one_sermon_without_passage_fails_100_percent(all_souls):
    strict = dataclasses.replace(all_souls, min_book_share=1.0)
    series, report = _series(strict, _romans_run(["Romans 1", "Romans 2", "Romans 3", "Romans 4", None]))
    assert series == []
    assert any("no passage" in v for v in report.skipped_series.values())


def test_backfilled_sermon_joins_its_series(all_souls):
    old = RawSermon(
        source_key="1",
        origin="scrape",
        title="Earlier part",
        date=date(2026, 9, 6),
        speaker="Charlie Skrine",
        series_name="No Favourites",
        series_label_explicit=True,
        passage_text="Acts 9:20–31",
        audio_url="https://www.allsouls.org/Media/PlayMedia.aspx?download=file&media_id=1&file_id=2",
    )
    from .conftest import FakeFetcher

    sermons, _ = collect(all_souls, FakeFetcher())
    church, _ = build_church(all_souls, [*sermons, old], TODAY)
    nf = next(s for s in church["series"] if s["title"] == "No Favourites")
    assert nf["sermons"][0]["id"] == "all-souls-langham-place-1"
    assert nf["startDate"] == "2026-09-06"


def test_example_library_is_valid():
    assert validate_library(json.loads(EXAMPLE.read_text(encoding="utf-8"))) == []


def test_integrity_checks_catch_bad_refs():
    lib = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    bad = copy.deepcopy(lib)
    bad["series"][0]["sermons"][0]["speakerId"] = "nobody"
    assert any("unknown speakerId nobody" in p for p in validate_library(bad))
    bad = copy.deepcopy(lib)
    bad["series"][0]["sermons"].reverse()
    assert any("preached order" in p for p in validate_library(bad))


def test_validator_enforces_book_share_span_and_gaps():
    lib = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    bad = copy.deepcopy(lib)
    bad["series"][0]["sermons"][0]["passage"]["display"] = "Galatians 1:1-5"
    assert any("is not in book Rom" in p for p in validate_library(bad))  # book must match display
    bad = copy.deepcopy(lib)
    del bad["series"][0]["sermons"][0]["passage"]  # 3/5 in Romans
    assert any("only 3/5 sermons in Rom" in p for p in validate_library(bad))
    bad = copy.deepcopy(lib)
    bad["series"][0]["sermons"][-1]["date"] = bad["series"][0]["endDate"] = "2026-06-01"
    assert any("gap of more than a year" in p for p in validate_library(bad))
