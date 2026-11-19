"""Collect (RSS first, scrape backfill), group into book series, emit library.json."""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from . import policy
from .config import SourceConfig
from .http import Fetcher
from .models import RawSermon
from .normalize import series_key, slugify
from .rss import parse_feed
from .scrapers import get_scraper
from .scripture import Reference, parse_references

log = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0.0"
LOOK_FORWARD_DAYS = 365  # a sermon continues a series if the previous one was at most this long before
MAX_SPAN_DAYS = 3 * 365 + 1  # whole series (first to last sermon) within 3 years
IN_PROGRESS_DAYS = 28  # last sermon this recent => isComplete false


# --- collect --------------------------------------------------------------------------------


def collect(
    cfg: SourceConfig, fetcher: Fetcher, *, scrape: bool = True, archive_pages: int = 0
) -> tuple[list[RawSermon], policy.MergeReport]:
    rss_items: list[RawSermon] = []
    for url in cfg.rss_urls:
        # Any exception here propagates: policy rule 2, never fall back to scraping.
        items = parse_feed(fetcher.get(url), cfg.rss_format)
        policy.require_feed_items(cfg, items, url)
        rss_items.extend(items)

    scraped: list[RawSermon] = []
    if scrape and cfg.scraper:
        scraper = get_scraper(cfg.scraper)(cfg, fetcher, archive_pages=archive_pages, rss_items=rss_items)
        scraped = scraper.run()
        log.info("%s: scraper fetched %d pages", cfg.church_id, scraper.pages_fetched)

    merged, report = policy.merge_prefer_rss(rss_items, scraped)
    policy.assert_rss_precedence(rss_items, merged)
    log.info("%s: %s", cfg.church_id, report.summary())
    return merged, report


# --- group + emit ---------------------------------------------------------------------------


@dataclass
class BuildReport:
    published_series: list[str] = field(default_factory=list)
    skipped_series: dict[str, str] = field(default_factory=dict)  # name -> reason
    dropped_sermons: Counter[str] = field(default_factory=Counter)  # reason -> count
    kept_off_book: dict[str, int] = field(default_factory=dict)  # series -> sermons not in its book


def build_church(cfg: SourceConfig, sermons: list[RawSermon], today: date) -> tuple[dict, BuildReport]:
    report = BuildReport()
    aliases = {series_key(k): v for k, v in cfg.series_aliases.items()}
    excluded = {series_key(aliases.get(series_key(n), n)) for n in cfg.exclude_series}

    def canonical(name: str) -> str:
        return aliases.get(series_key(name), name)

    explicit_keys = {
        series_key(canonical(s.series_name)) for s in sermons if s.series_name and s.series_label_explicit
    }

    groups: dict[str, list[RawSermon]] = defaultdict(list)
    spellings: dict[str, Counter[str]] = defaultdict(Counter)
    for s in sermons:
        if s.speaker:
            s.speaker = cfg.speaker_aliases.get(s.speaker, s.speaker)
        if not s.series_name:
            report.dropped_sermons["no series"] += 1
            continue
        name = canonical(s.series_name)
        key = series_key(name)
        if not s.series_label_explicit and key not in explicit_keys:
            report.dropped_sermons["no series"] += 1
            continue
        groups[key].append(s)
        spellings[key][name] += 1

    series_out: list[dict] = []
    used_ids: set[str] = set()
    for key, members in groups.items():
        name = _display_name(key, spellings[key], aliases)
        if key in excluded or any(p.casefold() in name.casefold() for p in cfg.exclude_patterns):
            report.skipped_series[name] = "excluded in config"
            continue
        for run in _split_runs(members):
            label = f"{name} ({run[0].date or '?'})"
            built = _build_series(cfg, name, run, today, report, label)
            if built is None:
                continue
            sid = built["id"]
            if sid in used_ids:  # same name, book and start year: disambiguate by start month
                sid = f"{sid}-{built['startDate'][5:7]}"
                built["id"] = sid
            used_ids.add(sid)
            series_out.append(built)
            report.published_series.append(f"{name} [{built['book']}] x{len(built['sermons'])}")

    series_out.sort(key=lambda s: s["sermons"][-1]["date"], reverse=True)

    speaker_names: dict[str, str] = {}
    for s in sermons:
        if s.speaker:
            speaker_names.setdefault(slugify(s.speaker), s.speaker)
    used_speakers = {sp for se in series_out for sp in se["speakerIds"]}
    speakers = [
        {"id": sid, "name": speaker_names[sid]} for sid in sorted(used_speakers)
    ]
    church = {k: v for k, v in cfg.church.items() if k in {"id", "name", "location", "websiteUrl", "logoUrl"}}
    return {"church": church, "speakers": speakers, "series": series_out}, report


def _display_name(key: str, spellings: Counter[str], aliases: dict[str, str]) -> str:
    for target in aliases.values():
        if series_key(target) == key:
            return target
    return spellings.most_common(1)[0][0]


def _split_runs(members: list[RawSermon]) -> list[list[RawSermon]]:
    """1-year look-forward: a sermon continues the run if the previous one is <= 365 days earlier.

    A name reused after a longer silence starts a new series (e.g. 'Romans' in 1985 and 2012).
    """
    dated = sorted(
        (m for m in members if m.date), key=lambda m: (m.date, _talk_number(m.title), _media_order(m.source_key))
    )
    runs: list[list[RawSermon]] = []
    for m in dated:
        if runs and (m.date - runs[-1][-1].date).days <= LOOK_FORWARD_DAYS:
            runs[-1].append(m)
        else:
            runs.append([m])
    return runs


# Several talks on one date (a teaching day: "Romansfest Talk 1" ... "Talk 19", all 2001-03-01) are
# ordered by the number the source prints at the end of the title; their media ids don't follow it.
_TALK_NUMBER = re.compile(r"\bTalk\s+(\d+)\s*$", re.IGNORECASE)


def _talk_number(title: str | None) -> int:
    m = _TALK_NUMBER.search(title or "")
    return int(m[1]) if m else 0


def _media_order(key: str) -> tuple[int, str]:
    return (int(key), key) if key.isdigit() else (0, key)


def _build_series(
    cfg: SourceConfig, name: str, run: list[RawSermon], today: date, report: BuildReport, label: str
) -> dict | None:
    # A sermon may list several references ("Psalm 22:1-21; Mark 15:16-32"). It counts for a book
    # if ANY of them is in that book. The series needs min_book_share of its sermons in one book;
    # the rest (an OT interlude, a missing reference in the feed) stay in place, so one odd
    # sermon neither drops nor splits the series.
    all_refs = {s.source_key: parse_references(s.passage_text, s.listed_references) for s in run}
    books = Counter(b for rs in all_refs.values() for b in dict.fromkeys(r.book for r in rs))
    if not books:
        report.skipped_series[label] = "no parsable passages"
        return None
    book, n = books.most_common(1)[0]
    # Published passage: the first in-book reference, else the first reference, else none.
    refs: dict[str, Reference | None] = {
        k: next((r for r in rs if r.book == book), rs[0] if rs else None) for k, rs in all_refs.items()
    }
    share = n / len(run)
    unparsed = sum(1 for rs in all_refs.values() if not rs)
    if share < cfg.min_book_share:
        detail = dict(books) | ({"no passage": unparsed} if unparsed else {})
        report.skipped_series[label] = f"not one book: {share:.0%} {book} ({detail})"
        return None
    if n < len(run):
        report.kept_off_book[label] = len(run) - n

    span = (run[-1].date - run[0].date).days
    if span > MAX_SPAN_DAYS:
        report.skipped_series[label] = f"spans {span / 365.25:.1f} years (max 3)"
        return None

    end = run[-1].date
    in_progress = (today - end).days <= IN_PROGRESS_DAYS
    if len(run) < 2 and not (in_progress and run[0].series_label_explicit):
        report.skipped_series[label] = "single sermon"
        return None

    sermons_out = []
    for s in run:
        media = {
            k: v
            for k, v in (("audioUrl", s.audio_url), ("videoUrl", s.video_url), ("youtubeId", s.youtube_id))
            if v
        }
        if not media:
            report.dropped_sermons["no media"] += 1
            continue
        if not s.title or not s.speaker:
            report.dropped_sermons["missing title/speaker"] += 1
            continue
        out: dict = {
            "id": f"{cfg.church_id}-{slugify(s.source_key)}",
            "title": s.title,
            "date": s.date.isoformat(),
            "speakerId": slugify(s.speaker),
        }
        ref = refs[s.source_key]
        if ref is not None:
            out["passage"] = ref.to_passage()
        if s.duration_seconds:
            out["durationSeconds"] = s.duration_seconds
        if s.source_url:
            out["sourceUrl"] = s.source_url
        out["media"] = media
        sermons_out.append(out)
    if not sermons_out:
        report.skipped_series[label] = "no playable sermons"
        return None

    speaker_counts = Counter(s["speakerId"] for s in sermons_out)
    first_seen = {sid: i for i, sid in reversed(list(enumerate(s["speakerId"] for s in sermons_out)))}
    speaker_ids = sorted(speaker_counts, key=lambda sid: (-speaker_counts[sid], first_seen[sid]))

    series: dict = {
        "id": f"{cfg.church_id}-{book.lower()}-{run[0].date.year}-{slugify(name)}",
        "title": name,
        "book": book,
        "churchId": cfg.church_id,
        "speakerIds": speaker_ids,
    }
    images = Counter(s.image_url for s in run if s.image_url)
    if images:
        series["artworkUrl"] = images.most_common(1)[0][0]
    series_urls = Counter(s.series_url for s in run if s.series_url)
    series["sourceUrl"] = (
        series_urls.most_common(1)[0][0] if series_urls else (cfg.media_page_url or cfg.church["websiteUrl"])
    )
    series["startDate"] = sermons_out[0]["date"]
    series["endDate"] = sermons_out[-1]["date"]
    series["isComplete"] = not in_progress
    series["sermons"] = sermons_out
    return series


def build_library(churches: list[dict], generated_at: datetime | None = None) -> dict:
    generated_at = generated_at or datetime.now(timezone.utc)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "churches": [c["church"] for c in churches],
        # Speakers are global: the same preacher at two churches is one entry.
        "speakers": sorted({sp["id"]: sp for c in churches for sp in c["speakers"]}.values(), key=lambda sp: sp["id"]),
        "series": [se for c in churches for se in c["series"]],
    }
