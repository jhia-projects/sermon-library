"""St Helen's Bishopsgate (www.st-helens.org.uk) talk-page parser. BACKFILL ONLY.

Not registered as a build scraper yet: the church hasn't been added (no sources/*.toml, permission
pending). The feeds (api.st-helens.org.uk/v1.0/feeds/{sunday,midweek}.xml) carry only the last 20
talks each and no series, so the archive and series membership come from talk pages.

Pages (robots.txt checked 2026-11-17; no Crawl-delay):
  - /sitemap/talks, /sitemap/series  sitemap XML: every talk / series page URL
  - /resources/talk/<id>/            one talk: date+time, passage (<h2>), title (<h3>), speaker,
                                     series (with /resources/series/<id>/), audio download link
NEVER fetched: /resources/all/* (disallowed). Speaker links on talk pages point there; we only read
their text.

<id> is the same number as in the feed's audio URL (podcast-download/<id>/SE26-047.mp3), so it's
the source_key for both. Audio: keep the api.st-helens.org.uk download URL; it 302s to a *signed,
expiring* S3 URL, which must never be stored.
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from ..http import USER_AGENT as HTTP_USER_AGENT, Fetcher, RobotsDisallowed
from ..config import PIPELINE_DIR
from ..models import RawSermon
from ..normalize import collapse_ws
from ..scripture import parse_reference
from . import Scraper

log = logging.getLogger(__name__)

BASE = "https://www.st-helens.org.uk"
# Defence in depth on top of robots.txt: paths we refuse even if robots.txt can't be parsed right.
NEVER_FETCH_PREFIXES = ("/resources/all/", "/_util/login/")
SITEMAPS = {"talks": f"{BASE}/sitemap/talks", "series": f"{BASE}/sitemap/series"}

_TALK_PATH = re.compile(r"^/resources/talk/(\d+)/$")
_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
# "9 Aug 2026, 9.30am" / "28 Jun 1977, 1.10pm"; the time is optional.
_DATE = re.compile(r"^(\d{1,2} [A-Z][a-z]{2} \d{4})(?:,\s*(.+))?$")


def is_forbidden(url: str) -> bool:
    return urlsplit(url).path.startswith(NEVER_FETCH_PREFIXES)


def parse_sitemap(xml_text: str) -> list[str]:
    """<loc> URLs from a sitemap urlset, in document order."""
    root = ET.fromstring(xml_text)
    return [collapse_ws(loc.text) for loc in root.iter(f"{_SITEMAP_NS}loc") if loc.text and loc.text.strip()]


def talk_id(url: str) -> str | None:
    m = _TALK_PATH.match(urlsplit(url).path)
    return m.group(1) if m else None


def parse_talk_page(html: str, url: str) -> RawSermon:
    """One talk page -> RawSermon. Fields the page doesn't print are left empty."""
    tid = talk_id(url)
    if tid is None:
        raise ValueError(f"not a talk page url: {url}")
    soup = BeautifulSoup(html, "html.parser")
    info = soup.select_one("div.talk-info")
    if info is None:
        raise ValueError(f"{url}: no div.talk-info (page layout changed?)")

    def text(sel: str) -> str | None:
        el = info.select_one(sel)
        t = collapse_ws(el.get_text(" ", strip=True)) if el else ""
        return t or None

    when = _parse_date(text("div.date"))
    heading = text("h2")
    # <h2> is the site's passage slot. Keep it only if it parses as a reference (rule 5).
    passage = heading if heading and parse_reference(heading) else None

    speaker = series = series_url = None
    for p in info.find_all("p"):
        label = collapse_ws(p.get_text(" ", strip=True))
        a = p.find("a", href=True)
        if a is None:
            continue
        if label.startswith("Speaker:"):
            speaker = collapse_ws(a.get_text(" ", strip=True)) or None
        elif label.startswith("Series:"):
            series = collapse_ws(a.get_text(" ", strip=True)) or None
            series_url = urljoin(url, a["href"])

    audio = None
    og = soup.find("meta", property="og:audio")
    dl = info.find("a", attrs={"data-event": "download_talk"}, href=True)
    for cand in (dl["href"] if dl else None, og.get("content") if og else None):
        if cand and cand.startswith("https://") and "amazonaws.com" not in cand:
            audio = cand
            break

    return RawSermon(
        source_key=tid,
        origin="scrape",
        title=text("h3"),
        date=when,
        speaker=speaker,
        series_name=series,
        series_label_explicit=series is not None,  # printed as "Series: X"
        passage_text=passage,
        listed_references=passage,
        audio_url=audio,
        source_url=f"{BASE}/resources/talk/{tid}/",
        series_url=series_url,
    )


def page_extras(html: str) -> dict[str, object]:
    """Fields RawSermon has no slot for yet, reported by the crawl for review."""
    soup = BeautifulSoup(html, "html.parser")
    info = soup.select_one("div.talk-info")
    raw_date = info.select_one("div.date") if info else None
    m = _DATE.match(collapse_ws(raw_date.get_text(" ", strip=True))) if raw_date else None
    desc = info.find("p", recursive=False) if info else None
    return {
        "service_time": m.group(2) if m and m.group(2) else None,
        "has_video": soup.find("a", href=re.compile(r"/resources/talk/\d+/video/$")) is not None,
        "handout": bool(soup.find("a", attrs={"data-event": "talk_handout_download"})),
        "description": (collapse_ws(desc.get_text(" ", strip=True)) or None) if desc else None,
        "jsonld_blocks": len(soup.find_all("script", type="application/ld+json")),
    }


def _parse_date(s: str | None) -> date | None:
    m = _DATE.match(s or "")
    return datetime.strptime(m.group(1), "%d %b %Y").date() if m else None


# --- snapshot (the one-off crawl's committed result) ---------------------------------------

# Fields stored per talk: RawSermon data fields (minus ones talk pages never fill) + service time.
_SNAPSHOT_FIELDS = ("title", "date", "speaker", "series_name", "series_label_explicit", "passage_text",
                    "listed_references", "audio_url", "source_url", "series_url")


def snapshot_row(s: RawSermon, html: str) -> dict:
    row: dict[str, object] = {"source_key": s.source_key}
    for k in _SNAPSHOT_FIELDS:
        v = getattr(s, k)
        if v is not None and v is not False:
            row[k] = v.isoformat() if isinstance(v, date) else v
    if t := page_extras(html)["service_time"]:
        row["service_time"] = t
    return row


def write_snapshot(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda r: int(r["source_key"]))
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
    tmp.replace(path)


def read_snapshot(path: Path) -> list[RawSermon]:
    out: list[RawSermon] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        r.pop("service_time", None)
        if "date" in r:
            r["date"] = date.fromisoformat(r["date"])
        out.append(RawSermon(origin="scrape", **r))
    return out


# --- build scraper ----------------------------------------------------------------------------


class StHelensScraper(Scraper):
    """Snapshot of the one-off crawl + talk pages for feed talks the snapshot lacks.

    The feed gives the latest talks without series; their talk pages give the series. Each build
    fetches only the pages of feed talks that aren't in the snapshot (at most the feed's 20 items).
    """

    name = "sthelens"

    def run(self) -> list[RawSermon]:
        snap = read_snapshot(PIPELINE_DIR / self.cfg.snapshot) if self.cfg.snapshot else []
        have = {s.source_key for s in snap}
        out = list(snap)
        for item in self.rss_items:
            if item.source_key in have:
                continue
            url = f"{BASE}/resources/talk/{item.source_key}/"
            if is_forbidden(url):  # can't happen for /resources/talk/, but the guard is cheap
                continue
            have.add(item.source_key)
            try:
                out.append(parse_talk_page(self.fetch_page(url), url))
            except ValueError as e:  # layout change or odd page: that talk just gets no series
                log.warning("%s: skipped talk page: %s", self.cfg.church_id, e)
        log.info("%s: snapshot %d talks, %d talk pages parsed for new feed items",
                 self.cfg.church_id, len(snap), len(out) - len(snap))
        if self.cfg.sunday_only:
            out = [s for s in out if s.date is not None and s.date.weekday() == 6]
        return out


# --- crawl ----------------------------------------------------------------------------------

USER_AGENT = HTTP_USER_AGENT
SNAPSHOT = PIPELINE_DIR / "data" / "st-helens-bishopsgate" / "talks.jsonl"


def crawl(
    out_dir: Path,
    *,
    limit: int,
    ids: list[str] | None = None,
    newest_first: bool = False,
    snapshot: Path | None = SNAPSHOT,
    fetcher: Fetcher | None = None,
) -> dict:
    """Fetch the sitemaps and up to `limit` uncrawled talk pages (or exactly `ids`), cached under
    out_dir/cache, then rewrite the snapshot from *every* cached talk page.

    Re-running resumes: cached pages are never fetched again, and `limit` counts only new pages, so
    repeated runs walk further through the sitemap. Also writes talks.txt / series.txt (sitemap URL
    lists) to out_dir.
    """
    from ..crawl import CachedCrawler
    from ..http import PoliteFetcher

    if fetcher is None:
        fetcher = PoliteFetcher(USER_AGENT, min_delay=2.0, delay_jitter=1.0)  # 2-3s per request
    allowed = getattr(fetcher, "allowed", None)
    # Startup robots.txt check: the pages we need must be allowed, and the rule we rely on to
    # keep out of /resources/all/ must be in force (the hard guard below applies regardless).
    if allowed is not None:
        for url in [*SITEMAPS.values(), f"{BASE}/resources/talk/1/"]:
            if not allowed(url):
                raise RobotsDisallowed(f"robots.txt now disallows {url}; stopping")
        if allowed(f"{BASE}/resources/all/x"):
            log.warning("robots.txt no longer disallows /resources/all/; the hard guard still does")

    crawler = CachedCrawler(fetcher, out_dir / "cache", forbidden=is_forbidden, allowed=allowed)
    lists: dict[str, list[str]] = {}
    for name, url in SITEMAPS.items():
        body = crawler.get(url)
        if body is None:
            raise RuntimeError(f"sitemap {url} returned a client error")
        lists[name] = parse_sitemap(body)
        (out_dir / f"{name}.txt").write_text("\n".join(lists[name]) + "\n", encoding="utf-8")

    all_talks = [u for u in lists["talks"] if talk_id(u) and not is_forbidden(u)]
    if ids:
        known = {talk_id(u) for u in all_talks}
        if unknown := sorted(set(ids) - known):
            log.warning("ids not in /sitemap/talks: %s", unknown)
        todo = [f"{BASE}/resources/talk/{i}/" for i in ids]
    else:
        order = sorted(all_talks, key=lambda u: int(talk_id(u) or 0), reverse=newest_first)
        todo = [u for u in order if not crawler.cached(u)][:limit]

    errors: list[dict] = []
    for n, url in enumerate(todo, 1):
        html = crawler.get(url)
        if n % 50 == 0:
            log.info("crawled %d/%d", n, len(todo))
        if html is None:
            errors.append({"url": url, "error": "client error (cached)"})

    rows: list[dict] = []
    for url in all_talks:
        if not crawler.cached(url):
            continue
        html = crawler.get(url)
        if html is None:
            continue
        try:
            rows.append(snapshot_row(parse_talk_page(html, url), html))
        except ValueError as e:
            errors.append({"url": url, "error": str(e)})
    if snapshot is not None:
        write_snapshot(snapshot, rows)
    return {
        "sitemap_talks": len(lists["talks"]),
        "sitemap_series": len(lists["series"]),
        "crawled_talks": len(rows),
        "remaining": sum(not crawler.cached(u) for u in all_talks),
        "errors": errors,
        "network_requests": crawler.fetched,
    }
