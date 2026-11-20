"""St Helen's Bishopsgate: talk-page parser, robots guard and cached crawler (offline)."""

from __future__ import annotations

import dataclasses
import urllib.error
import urllib.robotparser
from datetime import date, timedelta
from pathlib import Path

import pytest

from sermon_pipeline.crawl import CachedCrawler
from sermon_pipeline.http import PoliteFetcher, RobotsDisallowed
from sermon_pipeline.scrapers import sthelens
from sermon_pipeline.scrapers.sthelens import (
    BASE,
    crawl,
    is_forbidden,
    page_extras,
    parse_sitemap,
    parse_talk_page,
    talk_id,
)

from .conftest import FIXTURES, FakeFetcher

SH = FIXTURES / "st-helens-bishopsgate"


def talk(tid: str):
    return parse_talk_page((SH / f"talk_{tid}.html").read_text(encoding="utf-8"), f"{BASE}/resources/talk/{tid}/")


# --- parser ---------------------------------------------------------------------------------


def test_modern_talk_page():
    s = talk("59476")
    assert s.source_key == "59476" and s.origin == "scrape"
    assert s.title == "Running from God—seeing grace"
    assert s.date == date(2026, 8, 9)
    assert s.speaker == "Paul Williams"
    assert s.passage_text == "Jonah 1:1-16"
    assert s.series_name == "Grasping grace" and s.series_label_explicit
    assert s.series_url == f"{BASE}/resources/series/5664/"
    assert s.audio_url == "https://api.st-helens.org.uk/v1.0/downloads/instant-download/59476/SP26-033.mp3"
    assert s.source_url == f"{BASE}/resources/talk/59476/"
    extras = page_extras((SH / "talk_59476.html").read_text(encoding="utf-8"))
    assert extras["service_time"] == "9.30am" and extras["has_video"] and extras["handout"]
    assert extras["jsonld_blocks"] == 0


def test_empty_passage_heading_gives_no_passage():
    # 1971 talks print <h2></h2>: the source has no reference, so we invent none (rule 5).
    s = talk("4")
    assert s.passage_text is None and s.listed_references is None
    assert s.title == "Lust" and s.date == date(1971, 1, 10) and s.speaker == "Ian Barclay"
    assert s.series_name == "A storm of spears"
    assert page_extras((SH / "talk_4.html").read_text(encoding="utf-8"))["description"] is None


def test_feed_audio_id_is_the_talk_page_id():
    # Feed enclosure .../podcast-download/59581/SA26-047.mp3 <-> /resources/talk/59581/: same talk.
    feed = (SH / "feed_sunday.xml").read_text(encoding="utf-8")
    assert "podcast-download/59581/SA26-047.mp3" in feed
    s = talk("59581")
    assert (s.title, s.speaker, s.passage_text, s.date) == (
        "God’s certain promise", "Nick Heeley", "Genesis 15:1-21", date(2026, 11, 15))
    assert s.series_name == "Saving the world"  # the feed has no series at all


def test_audio_url_never_signed_s3():
    for tid in ("4", "59476", "59581"):
        assert talk(tid).audio_url.startswith("https://api.st-helens.org.uk/")


def test_parse_sitemaps():
    talks = parse_sitemap((SH / "sitemap_talks.xml").read_text(encoding="utf-8"))
    series = parse_sitemap((SH / "sitemap_series.xml").read_text(encoding="utf-8"))
    assert talks[0] == f"{BASE}/resources/talk/2/" and len(talks) == 8
    assert all(talk_id(u) for u in talks)
    assert series[0] == f"{BASE}/resources/series/2/" and len(series) == 8


# --- robots / guard -------------------------------------------------------------------------


def fetcher_with_saved_robots() -> PoliteFetcher:
    f = PoliteFetcher(sthelens.USER_AGENT)
    rp = urllib.robotparser.RobotFileParser()
    rp.parse((SH / "robots.txt").read_text(encoding="utf-8").splitlines())
    f._robots[BASE] = rp
    return f


@pytest.mark.parametrize("path", ["/resources/all/", "/resources/all/speaker-61/Dick-Lucas/", "/_util/login/x"])
def test_disallowed_paths(path):
    assert is_forbidden(BASE + path)
    assert not fetcher_with_saved_robots().allowed(BASE + path)  # `Disallow: /resources/all/*` wildcard


@pytest.mark.parametrize("path", ["/resources/talk/1618/", "/resources/series/894/", "/sitemap/talks"])
def test_allowed_paths(path):
    assert not is_forbidden(BASE + path)
    assert fetcher_with_saved_robots().allowed(BASE + path)


def test_crawler_refuses_forbidden_without_a_request(tmp_path: Path):
    fake = FakeFetcher({})
    crawler = CachedCrawler(fake, tmp_path, forbidden=is_forbidden, allowed=lambda u: True)
    with pytest.raises(RobotsDisallowed):
        crawler.get(f"{BASE}/resources/all/speaker-61/Dick-Lucas/")
    assert fake.calls == []


def test_crawler_refuses_robots_disallowed_without_a_request(tmp_path: Path):
    fake = FakeFetcher({})
    crawler = CachedCrawler(fake, tmp_path, allowed=lambda u: False)
    with pytest.raises(RobotsDisallowed):
        crawler.get(f"{BASE}/resources/talk/1/")
    assert fake.calls == []


def test_polite_fetcher_rejects_delay_below_floor():
    with pytest.raises(ValueError):
        PoliteFetcher(min_delay=1.0)


# --- cache / resume -------------------------------------------------------------------------


class ErrorFetcher(FakeFetcher):
    def __init__(self, codes: dict[str, int]) -> None:
        super().__init__({})
        self.codes = codes

    def get(self, url: str) -> str:
        self.calls.append(url)
        raise urllib.error.HTTPError(url, self.codes[url], "err", {}, None)  # type: ignore[arg-type]


def test_cache_means_each_url_fetched_once(tmp_path: Path):
    url = f"{BASE}/resources/talk/4/"
    fake = FakeFetcher({url: SH / "talk_4.html"})
    first = CachedCrawler(fake, tmp_path)
    body = first.get(url)
    second = CachedCrawler(fake, tmp_path)  # a later run, same cache
    assert second.get(url) == body
    assert fake.calls == [url] and second.fetched == 0 and second.cache_hits == 1


def test_client_errors_cached_server_errors_retried(tmp_path: Path):
    gone, broken = f"{BASE}/resources/talk/3/", f"{BASE}/resources/talk/8/"
    fake = ErrorFetcher({gone: 404, broken: 503})
    crawler = CachedCrawler(fake, tmp_path)
    assert crawler.get(gone) is None and crawler.get(gone) is None
    for _ in range(2):
        with pytest.raises(urllib.error.HTTPError):
            crawler.get(broken)
    assert fake.calls == [gone, broken, broken]


def crawl_pages() -> dict[str, Path]:
    return {
        sthelens.SITEMAPS["talks"]: SH / "sitemap_talks.xml",
        sthelens.SITEMAPS["series"]: SH / "sitemap_series.xml",
        f"{BASE}/resources/talk/2/": SH / "talk_4.html",  # any talk page body will do here
        f"{BASE}/resources/talk/4/": SH / "talk_4.html",
        f"{BASE}/resources/talk/5/": SH / "talk_4.html",
    }


def test_crawl_resumes_and_limit_counts_new_pages(tmp_path: Path):
    fake = FakeFetcher(crawl_pages())
    snap = tmp_path / "talks.jsonl"
    first = crawl(tmp_path, limit=2, snapshot=snap, fetcher=fake)
    assert first["network_requests"] == 4 and first["crawled_talks"] == 2
    assert (tmp_path / "talks.txt").read_text().splitlines()[0] == f"{BASE}/resources/talk/2/"
    second = crawl(tmp_path, limit=1, snapshot=snap, fetcher=fake)  # walks on to talk 5
    assert second["network_requests"] == 1 and second["crawled_talks"] == 3
    assert fake.calls.count(f"{BASE}/resources/talk/4/") == 1
    # The snapshot holds every cached talk, sorted by id, and reads back as scraped sermons.
    keys = [s.source_key for s in sthelens.read_snapshot(snap)]
    assert keys == ["2", "4", "5"]


def test_crawl_with_empty_cache_adds_to_the_snapshot(tmp_path: Path):
    """CI has no page cache: a crawl must add new talks and keep the snapshot's rows, never shrink
    the snapshot to the pages it happened to fetch."""
    snap = tmp_path / "talks.jsonl"
    crawl(tmp_path / "a", limit=2, snapshot=snap, fetcher=FakeFetcher(crawl_pages()))  # talks 2, 4
    fake = FakeFetcher(crawl_pages())
    crawl(tmp_path / "b", limit=5, snapshot=snap, fetcher=fake)  # fresh cache
    assert f"{BASE}/resources/talk/2/" not in fake.calls  # already in the snapshot: not re-fetched
    assert [s.source_key for s in sthelens.read_snapshot(snap)] == ["2", "4", "5"]


def test_crawl_newest_first(tmp_path: Path):
    pages = crawl_pages() | {f"{BASE}/resources/talk/59583/": SH / "talk_4.html"}
    fake = FakeFetcher(pages)
    crawl(tmp_path, limit=1, newest_first=True, snapshot=None, fetcher=fake)
    assert fake.calls[-1] == f"{BASE}/resources/talk/59583/"


def test_snapshot_round_trip(tmp_path: Path):
    html = (SH / "talk_59476.html").read_text(encoding="utf-8")
    s = parse_talk_page(html, f"{BASE}/resources/talk/59476/")
    row = sthelens.snapshot_row(s, html)
    assert row["service_time"] == "9.30am" and "description" not in row
    sthelens.write_snapshot(tmp_path / "t.jsonl", [row])
    (back,) = sthelens.read_snapshot(tmp_path / "t.jsonl")
    assert back.values() == s.values() and back.origin == "scrape"


# --- RSS feeds ------------------------------------------------------------------------------

from sermon_pipeline.build import collect  # noqa: E402
from sermon_pipeline.config import SOURCES_DIR, SourceConfig, load_source  # noqa: E402
from sermon_pipeline.policy import PolicyError  # noqa: E402
from sermon_pipeline.rss import parse_feed  # noqa: E402

SUNDAY = "https://api.st-helens.org.uk/v1.0/feeds/sunday.xml"
MIDWEEK = "https://api.st-helens.org.uk/v1.0/feeds/midweek.xml"


def feed(name: str):
    return parse_feed((SH / f"feed_{name}.xml").read_text(encoding="utf-8"), "sthelens")


def test_sunday_feed_items():
    items = feed("sunday")
    assert len(items) == 20
    s = items[1]
    assert s.source_key == "59581" and s.origin == "rss"
    assert (s.title, s.speaker, s.passage_text, s.date) == (
        "God’s certain promise", "Nick Heeley", "Genesis 15:1-21", date(2026, 11, 15))
    assert s.audio_url == "https://api.st-helens.org.uk/v1.0/downloads/podcast-download/59581/SA26-047.mp3"
    assert s.duration_seconds == 1761
    # The feed prints no series and no page link: nothing is invented for them.
    assert all(i.series_name is None and i.source_url is None for i in items)
    # Leading space in the source title (" The Son was before Abraham", 9am) is trimmed.
    assert items[3].title == "The Son was before Abraham"


def test_midweek_feed_items_have_no_service_time():
    items = feed("midweek")
    assert len(items) == 20
    assert (items[0].source_key, items[0].passage_text, items[0].speaker) == ("59570", "Acts 4:23-37", "Paul Williams")
    assert all(i.passage_text and i.speaker and i.audio_url for i in items)


def test_feed_and_talk_page_share_source_key():
    by_key = {s.source_key: s for s in feed("sunday")}
    page = talk("59581")
    assert by_key[page.source_key].passage_text == page.passage_text


def test_subtitle_without_reference_gives_no_passage():
    xml = (SH / "feed_midweek.xml").read_text(encoding="utf-8").replace(
        "Acts 4:23-37 - Paul Williams", "Special evening - Paul Williams", 1)
    first = parse_feed(xml, "sthelens")[0]
    assert first.passage_text is None and first.speaker == "Paul Williams"


def test_generic_format_unchanged_for_st_helens_feed():
    # Pins why the sthelens format exists: the generic reader keys by URL and finds no passage.
    s = parse_feed((SH / "feed_sunday.xml").read_text(encoding="utf-8"))[1]
    assert s.source_key.startswith("https://") and s.passage_text is None


@pytest.fixture
def st_helens() -> SourceConfig:
    return load_source(SOURCES_DIR / "st-helens-bishopsgate.toml")


def test_source_config_is_sunday_only(st_helens):
    assert st_helens.rss_urls == (SUNDAY,) and st_helens.rss_format == "sthelens"
    assert st_helens.scraper == "sthelens" and st_helens.sunday_only
    assert st_helens.snapshot == "data/st-helens-bishopsgate/talks.jsonl"


def with_snapshot(cfg: SourceConfig, path: Path) -> SourceConfig:
    return dataclasses.replace(cfg, snapshot=str(path))  # absolute path wins over PIPELINE_DIR


def test_feed_talk_gets_its_series_from_its_talk_page(st_helens, tmp_path: Path):
    page = f"{BASE}/resources/talk/59581/"
    f = FakeFetcher({SUNDAY: SH / "feed_sunday.xml", page: SH / "talk_59581.html"})
    sermons, report = collect(with_snapshot(st_helens, tmp_path / "none.jsonl"), f)
    # Feed first, then the talk page of every feed talk (19 of them are blank pages here: skipped).
    assert f.calls[0] == SUNDAY and len(f.calls) == 21 and page in f.calls
    s = next(x for x in sermons if x.source_key == "59581")
    assert s.origin == "rss" and s.series_name == "Saving the world" and s.series_label_explicit
    assert s.provenance["series_name"] == "scrape" and s.provenance["passage_text"] == "rss"
    # The feed's audio URL stays (RSS wins); the page's differing one is discarded and counted.
    assert s.audio_url.endswith("/podcast-download/59581/SA26-047.mp3")
    assert s.source_url == page and report.ignored_conflicts["audio_url"] == 1
    assert len(sermons) == 20 and report.backfilled == 0


def test_feed_talk_in_snapshot_is_not_refetched(st_helens, tmp_path: Path):
    html = (SH / "talk_59581.html").read_text(encoding="utf-8")
    row = sthelens.snapshot_row(parse_talk_page(html, f"{BASE}/resources/talk/59581/"), html)
    sthelens.write_snapshot(tmp_path / "s.jsonl", [row])
    f = FakeFetcher({SUNDAY: SH / "feed_sunday.xml"})
    sermons, _ = collect(with_snapshot(st_helens, tmp_path / "s.jsonl"), f)
    assert f"{BASE}/resources/talk/59581/" not in f.calls and len(f.calls) == 20
    assert next(x for x in sermons if x.source_key == "59581").series_name == "Saving the world"


def test_sunday_only_drops_midweek_archive_talks(st_helens, tmp_path: Path):
    rows = []
    for tid in ("4", "59476"):  # 4: Sun 10 Jan 1971; 59476: Sun 9 Aug 2026
        html = (SH / f"talk_{tid}.html").read_text(encoding="utf-8")
        rows.append(sthelens.snapshot_row(parse_talk_page(html, f"{BASE}/resources/talk/{tid}/"), html))
    rows.append({**rows[0], "source_key": "1618", "date": "1977-06-28"})  # a Tuesday lunchtime talk
    sthelens.write_snapshot(tmp_path / "s.jsonl", rows)
    f = FakeFetcher({SUNDAY: SH / "feed_sunday.xml"})
    sermons, report = collect(with_snapshot(st_helens, tmp_path / "s.jsonl"), f)
    keys = {s.source_key for s in sermons}
    assert {"4", "59476"} <= keys and "1618" not in keys and report.backfilled == 2


def test_one_empty_feed_of_two_fails_the_build():
    cfg = SourceConfig.from_dict({"church": {"id": "x", "name": "X", "websiteUrl": "https://x.org"},
                                  "rss": {"urls": [SUNDAY, MIDWEEK], "format": "sthelens"}})
    empty = '<?xml version="1.0"?><rss version="2.0"><channel><title>x</title></channel></rss>'
    f = FakeFetcher({SUNDAY: SH / "feed_sunday.xml", MIDWEEK: empty})
    with pytest.raises(PolicyError, match="midweek.xml returned no sermons"):
        collect(cfg, f, scrape=False)


@pytest.mark.parametrize("rss, match", [
    ({"url": SUNDAY, "urls": [SUNDAY, MIDWEEK]}, "not both"),
    ({"urls": [SUNDAY, "http://api.st-helens.org.uk/x.xml"]}, "must be https"),
    ({"urls": [SUNDAY, SUNDAY]}, "duplicate RSS url"),
    ({"url": SUNDAY, "format": "nope"}, "unknown"),
])
def test_bad_feed_configs_rejected(rss, match):
    with pytest.raises((PolicyError, ValueError), match=match):
        SourceConfig.from_dict({"church": {"id": "x", "name": "X", "websiteUrl": "https://x.org"}, "rss": rss})


# --- repeated services (series rule: one copy per date per morning/evening) -----------------

from sermon_pipeline.build import build_church, service_minutes  # noqa: E402
from sermon_pipeline.config import SOURCES_DIR, load_source  # noqa: E402
from sermon_pipeline.rss import parse_feed  # noqa: E402


@pytest.mark.parametrize(
    "text, mins",
    [("9.30am", 570), ("9am", 540), ("11:15am", 675), ("4pm", 960), ("6pm", 1080), ("6.30pm", 1110),
     ("12 noon", 720), ("12.15pm", 735), (None, None), ("evening", None), ("13pm", None)],
)
def test_service_minutes(text, mins):
    assert service_minutes(text) == mins


def test_service_time_from_feed_and_page():
    items = {s.source_key: s for s in parse_feed((SH / "feed_sunday.xml").read_text(encoding="utf-8"), "sthelens")}
    assert items["59582"].service_time == "6pm" and items["59579"].service_time == "11:15am"
    assert talk("59476").service_time == "9.30am"


def feed_series() -> list:
    """The live Sunday feed (2026-11-15 back) with the series its talk pages print."""
    names = {"John": "God sent his Son", "Luke": "Such a great salvation"}
    out = []
    for s in parse_feed((SH / "feed_sunday.xml").read_text(encoding="utf-8"), "sthelens"):
        book = (s.passage_text or "").split(" ")[0]
        if book in names:
            out.append(dataclasses.replace(s, series_name=names[book], series_label_explicit=True, provenance={}))
    return out


def test_repeated_services_keep_one_copy_per_half_day():
    # Motivating case: John 8:48-59 preached at 9am (59580) and 11:15am (59579) on 15 Nov 2026;
    # Luke 8:40-56 at 4pm (59573) and 6pm (59574) on 8 Nov. Each Sunday was listed twice.
    cfg = load_source(SOURCES_DIR / "st-helens-bishopsgate.toml")
    assert cfg.one_per_service_half
    church, report = build_church(cfg, feed_series(), date(2026, 11, 19))
    by_name = {s["title"]: s for s in church["series"]}
    john, luke = by_name["God sent his Son"], by_name["Such a great salvation"]
    for se in (john, luke):
        dates = [x["date"] for x in se["sermons"]]
        assert len(dates) == len(set(dates)), se["title"]
    ids = {x["id"] for se in church["series"] for x in se["sermons"]}
    assert "st-helens-bishopsgate-59580" in ids and "st-helens-bishopsgate-59579" not in ids  # 9am kept
    assert "st-helens-bishopsgate-59573" in ids and "st-helens-bishopsgate-59574" not in ids  # 4pm kept
    assert report.dropped_sermons["repeated service"] == sum(report.repeated_services.values()) > 0


def test_repeated_services_rule_is_off_by_default():
    cfg = dataclasses.replace(load_source(SOURCES_DIR / "st-helens-bishopsgate.toml"), one_per_service_half=False)
    church, report = build_church(cfg, feed_series(), date(2026, 11, 19))
    assert not report.repeated_services
    assert sum(len(se["sermons"]) for se in church["series"]) == len(feed_series())


def _services_only():
    """The St Helen's config with just the repeated-service rule (these fixtures are tiny same-day
    series, which the weekend/same-day rule would judge separately)."""
    return dataclasses.replace(load_source(SOURCES_DIR / "st-helens-bishopsgate.toml"), event_patterns=())


def test_morning_and_evening_copies_both_stay():
    cfg = _services_only()
    am, pm = [s for s in feed_series() if s.date == date(2026, 11, 15)][:1] * 2
    am = dataclasses.replace(am, source_key="1", service_time="10.30am", provenance={})
    pm = dataclasses.replace(pm, source_key="2", service_time="6.30pm", provenance={})
    other = dataclasses.replace(am, source_key="3", date=date(2026, 11, 8), provenance={})
    church, report = build_church(cfg, [am, pm, other], date(2026, 11, 19))
    assert not report.repeated_services and len(church["series"][0]["sermons"]) == 3


def test_copy_without_a_service_time_is_never_dropped():
    cfg = _services_only()
    base = [s for s in feed_series() if s.date == date(2026, 11, 15) and s.passage_text.startswith("John")]
    unknown = [dataclasses.replace(s, service_time=None, provenance={}) for s in base]
    church, report = build_church(cfg, unknown, date(2026, 11, 19))
    assert not report.repeated_services and len(church["series"][0]["sermons"]) == 2


@pytest.mark.parametrize(
    "name, out",
    [("The gospel goes viral (4pm)", "The gospel goes viral"), ("God's king rising (10am)", "God's king rising"),
     ("Christianity 101 (10.30am)", "Christianity 101"), ("The knowledge of God: 4pm weekend", "The knowledge of God: 4pm weekend"),
     ("Psalms (part 2)", "Psalms (part 2)"), ("Acts (13pm)", "Acts (13pm)")],
)
def test_strip_service_suffix(name, out):
    from sermon_pipeline.build import strip_service_suffix
    assert strip_service_suffix(name) == out


def test_series_labelled_per_service_merge_into_one():
    # Motivating case (2021-09 on): the church labelled "The gospel goes viral (4pm)" and "(6pm)"
    # separately, so the same Acts series was published twice.
    cfg = load_source(SOURCES_DIR / "st-helens-bishopsgate.toml")
    base = feed_series()[0]
    rows = []
    for i, (d, t) in enumerate([(5, "4pm"), (5, "6pm"), (12, "4pm"), (12, "6pm")]):
        rows.append(dataclasses.replace(
            base, source_key=str(100 + i), date=date(2021, 9, d), service_time=t, passage_text=f"Acts {d}:1-10",
            listed_references=None, series_name=f"The gospel goes viral ({t})", provenance={}))
    church, report = build_church(cfg, rows, date(2026, 11, 19))
    (se,) = church["series"]
    assert se["title"] == "The gospel goes viral" and [s["id"][-3:] for s in se["sermons"]] == ["100", "102"]
    assert report.repeated_services == {"The gospel goes viral": 2}
    off = dataclasses.replace(cfg, one_per_service_half=False)
    assert len(build_church(off, rows, date(2026, 11, 19))[0]["series"]) == 2


# --- weekend / same-day series and placeholder dates ---------------------------------------

from sermon_pipeline.models import RawSermon  # noqa: E402


def _sermons(series: str, rows: list[tuple[str, str, str, str]]) -> list[RawSermon]:
    return [
        RawSermon(
            source_key=key, origin="scrape", title=title, date=date.fromisoformat(d), speaker="A Speaker",
            series_name=series, series_label_explicit=True, passage_text=ref,
            audio_url=f"https://example.org/{key}.mp3",
        )
        for key, d, title, ref in rows
    ]


LORDS_PRAYER = _sermons("The Lord's Prayer", [  # 2023: Matthew 18, then Matthew 4, same Sunday
    ("58073", "2023-02-12", "Prioritising forgiveness", "Matthew 18:21-35"),
    ("58074", "2023-02-12", "Knowing what matters", "Matthew 4:1-11"),
])
LOVE_OF_GOD = _sermons("Love of God", [  # 2023: works forward through Romans 8
    ("58152", "2023-05-14", "Working for good", "Romans 8:18-30"),
    ("58153", "2023-05-14", "No separation", "Romans 8:31-39"),
])
RML_1THESS = _sermons("1 Thessalonians: RML Overview weekend", [  # the same two passages, 2014 and 2015
    ("54139", "2014-11-23", "1 Thessalonians 4:13-5:11", "1 Thessalonians 4:13-5:11"),
    ("54140", "2014-11-23", "1 Thessalonians 5:23-24", "1 Thessalonians 5:23-24"),
    ("54642", "2015-11-15", "1 Thessalonians 4:13 - 5:11", "1 Thessalonians 4:13 - 5:11"),
    ("54643", "2015-11-15", "1 Thessalonians 5:23-24", "1 Thessalonians 5:23-24"),
])
STOTT_1THESS = _sermons("Studies in 1 Thessalonians", [  # all three dated 1978-01-01 by the site
    ("3081", "1978-01-01", "Christian evangelism", "1 Thessalonians 1:1-10"),
    ("3082", "1978-01-01", "Christian ministry", "1 Thessalonians 2:1-3:13"),
    ("3083", "1978-01-01", "Christian community", "1 Thessalonians 5:1-28"),
])


def _titles(cfg, sermons):
    church, report = build_church(cfg, sermons, date(2026, 11, 19))
    return [se["title"] for se in church["series"]], report


def test_same_day_series_kept_only_if_it_works_through_the_book():
    cfg = load_source(SOURCES_DIR / "st-helens-bishopsgate.toml")
    titles, report = _titles(cfg, LORDS_PRAYER + LOVE_OF_GOD + RML_1THESS)
    assert titles == ["Love of God"]
    assert report.skipped_series["The Lord's Prayer (2023-02-12)"].startswith("topical event series")
    assert report.skipped_series["1 Thessalonians: RML Overview weekend (2014-11-23)"].startswith("topical")


def test_weekend_label_alone_triggers_the_check():
    cfg = load_source(SOURCES_DIR / "st-helens-bishopsgate.toml")
    spread = [dataclasses.replace(s, date=s.date + timedelta(days=7 * i)) for i, s in enumerate(LORDS_PRAYER)]
    weekend = [dataclasses.replace(s, series_name="Prayer: City weekend") for s in spread]
    assert _titles(cfg, spread)[0] == ["The Lord's Prayer"]  # weekly, unlabelled: not an event
    assert _titles(cfg, weekend)[0] == []


def test_placeholder_date_series_skipped():
    cfg = load_source(SOURCES_DIR / "st-helens-bishopsgate.toml")
    titles, report = _titles(cfg, STOTT_1THESS)
    assert titles == [] and report.skipped_series["Studies in 1 Thessalonians (1978-01-01)"].startswith("placeholder")
    one = [dataclasses.replace(s, date=date(1978, 1, 1) + timedelta(days=7 * i)) for i, s in enumerate(STOTT_1THESS)]
    assert _titles(cfg, one)[0] == ["Studies in 1 Thessalonians"]  # one real 1 January Sunday is fine


def test_event_and_placeholder_rules_off_by_default():
    cfg = dataclasses.replace(
        load_source(SOURCES_DIR / "st-helens-bishopsgate.toml"), event_patterns=(), placeholder_dates=()
    )
    assert len(_titles(cfg, LORDS_PRAYER + RML_1THESS + STOTT_1THESS)[0]) == 3
