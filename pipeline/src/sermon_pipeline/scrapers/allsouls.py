"""All Souls Langham Place (Hubb CMS) backfill scraper.

Pages used (allowed by robots.txt, Crawl-delay 10s):
  - GET  /Media/AllMedia.aspx        listing page 1 (10 most recent). Gives each recording's
                                     series page link and YouTube link.
  - GET  /Groups/<id>/<Series>.aspx  series page: every sermon in that series.
  - POST /Media/AllMedia.aspx        archive listing pages 2..N (ASP.NET postback paging,
                                     ~646 pages back to the 1970s). Only when archive_pages > 0.
Plus the committed archive (`snapshot` in the source config): every sermon seen by earlier scrapes,
seeded from the full crawl, so a normal build needs only page 1 and the series pages.

Audio for sermons not in the feed uses the site's own download link
(/Media/PlayMedia.aspx?download=file&media_id=M&file_id=F), which 302s to the same MP3 the feed uses.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ..models import RawSermon
from ..snapshot import read_snapshot
from ..normalize import clean_title, collapse_ws, parse_duration, parse_series_label, series_key, youtube_id
from . import Scraper

_PLAY = re.compile(r"playMedia\(\s*(\d+)\s*,\s*(\d+)")
# Archive rows give only a rounded length: "Length: 29 minutes", "Length: 1 hour 12 minutes", "Length: 0 minute".
_LENGTH = re.compile(r"^(?:(\d+)\s*hours?\s*)?(\d+)\s*minutes?$")


class AllSoulsScraper(Scraper):
    name = "allsouls"
    updates_snapshot = True

    def run(self) -> list[RawSermon]:
        out: list[RawSermon] = []
        series_pages: list[str] = []
        if self.cfg.media_page_url:
            first = self.fetch_page(self.cfg.media_page_url)
            rows = parse_media_listing(first, self.cfg.media_page_url)
            out.extend(rows)
            series_pages.extend(r.series_url for r in rows if r.series_url)
            if self.archive_pages > 0:
                out.extend(self._crawl_archive(first))
        # The committed archive goes after the listing pages and before the series pages: the same
        # place the archive listing pages it was made from had, so a build from it matches a full crawl.
        if self.cfg.snapshot_path:
            out.extend(read_snapshot(self.cfg.snapshot_path))
        series_pages.extend(self.cfg.series_pages)
        for url in dict.fromkeys(series_pages):  # de-dupe, keep order
            out.extend(parse_series_page(self.fetch_page(url), url))
        return out

    def _crawl_archive(self, first_page: str) -> list[RawSermon]:
        """Listing pages 2..archive_pages+1. Each postback reuses the previous page's form state."""
        url = self.cfg.media_page_url
        assert url
        total = page_count(first_page)
        html, out = first_page, []
        for page in range(2, min(total, self.archive_pages + 1) + 1):
            html = self.post_page(url, archive_form(html, page))
            rows = parse_media_listing(html, url)
            if not rows:
                break
            out.extend(rows)
        return out


_PAGE_FIELD = "ctl00$ctl00$cphBody$cphSharedContents$hidden_page"
_SORT_FIELD = "ctl00$ctl00$cphBody$cphSharedContents$hidden_sort"


def archive_form(html: str, page: int, sort: str | None = None) -> dict[str, str]:
    """Postback fields to request listing page `page` (1-based) from a listing page's form.

    Carries over ASP.NET state (__VIEWSTATE etc.) and the current filter values unchanged.
    """
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", id="frm1")
    if form is None:
        raise ValueError("media listing form not found")
    data: dict[str, str] = {}
    for el in form.find_all(["input", "select"]):
        name = el.get("name")
        if not name or name == "searchSite" or el.get("type") in {"submit", "button"}:
            continue
        if el.name == "select":
            opt = el.find("option", selected=True) or el.find("option")
            data[name] = opt.get("value", "") if opt else ""
        else:
            data[name] = el.get("value", "")
    data[_PAGE_FIELD] = str(page)
    if sort:
        data[_SORT_FIELD] = sort
    return data


def page_count(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    return len(soup.select("#media_pager_top select option")) or 1


def parse_length(text: str) -> int | None:
    """'29 minutes' / '1 hour 12 minutes' -> seconds. '0 minute' and anything else -> None."""
    m = _LENGTH.match(text.strip())
    if not m:
        return None
    return (int(m[1] or 0) * 60 + int(m[2])) * 60 or None


def _download_url(base: str, media_id: str, file_id: str) -> str:
    return urljoin(base, f"/Media/PlayMedia.aspx?download=file&media_id={media_id}&file_id={file_id}")


def _https(url: str | None) -> str | None:
    return url if url and url.startswith("https://") else None


def parse_media_listing(html: str, page_url: str) -> list[RawSermon]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[RawSermon] = []
    for row in soup.select("div.media_recording"):
        title_a = row.select_one(".media_recording_title a")
        m = _PLAY.search(title_a.get("onclick", "")) if title_a else None
        if not title_a or not m:
            continue
        media_id = m[1]
        series, explicit = parse_series_label(_txt(row.select_one(".media_recording_descr")))

        series_url = None
        if series:
            for a in row.select("ul.media_recording_links a[href]"):
                # Link text may carry a catalogue code: "ZA008 Genesis" for series "Genesis".
                link_key = series_key(a.get_text())
                if link_key == series_key(series) or link_key.endswith(" " + series_key(series)):
                    series_url = urljoin(page_url, a["href"])
                    break

        audio = duration = yt = None
        for f in row.select(".media_recording_file"):
            fmt = _txt(f.select_one(".media_recording_file_format")) or ""
            label = f"{_txt(f.select_one('.media_recording_file_title')) or ''} {fmt}"
            dl = f.select_one("a.media_recording_file_download[href]")
            # Recent rows: "MP3 Audio 13.5MB (28:49)"; archive rows: title "MP3 Audio", format "64Kbps 13.4MB".
            if dl and re.search(r"audio|mp3|kbps", label, re.I) and audio is None:
                audio = urljoin(page_url, dl["href"])
                if dm := re.search(r"\((\d+(?::\d+){1,2})\)", fmt):
                    duration = parse_duration(dm[1])
            for a in f.select("a[href]"):
                yt = yt or youtube_id(a["href"])

        recorded = refs = length = None
        for li in row.select("ul.media_recording_details li"):
            text = collapse_ws(li.get_text(" "))
            if text.startswith("Recorded:"):
                recorded = _parse_date(text.removeprefix("Recorded:").strip(), "%d/%m/%Y")
            elif text.startswith("Length:"):
                length = parse_length(text.removeprefix("Length:"))
            elif text.startswith(("References:", "Reference:")):
                refs = [t for a in li.find_all("a") if (t := _txt(a))]

        img = row.select_one(".media_summary_image img[src]")
        out.append(
            RawSermon(
                source_key=media_id,
                origin="scrape",
                title=clean_title(title_a.get_text()) or None,
                date=recorded,
                speaker=_txt(row.select_one("a.media_recording_speaker")),
                series_name=series,
                series_label_explicit=explicit,
                passage_text=refs[0] if refs else None,
                listed_references="; ".join(refs) if refs else None,
                audio_url=_https(audio),
                youtube_id=yt,
                duration_seconds=duration or length,  # exact (mm:ss) when printed, else the rounded Length
                image_url=_https(urljoin(page_url, img["src"])) if img else None,
                series_url=_https(series_url),
                # Listing rows link to no page of their own (the feed's Player.aspx link exists only for
                # feed items): attribute to the series page that lists the sermon, else to the listing page.
                source_url=_https(series_url or page_url),
            )
        )
    return out


def parse_series_page(html: str, page_url: str) -> list[RawSermon]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[RawSermon] = []
    for title_div in soup.select("div.recent-sermon-title"):
        block = title_div.parent
        a = title_div.find("a", href=True)
        m = _PLAY.search(a["href"]) if a else None
        if not isinstance(block, Tag) or not m:
            continue
        media_id, file_id = m[1], m[2]
        series, explicit = parse_series_label(_txt(block.select_one(".recent-sermon-description")))
        bible = block.select_one(".recent-sermon-bible")
        lines: list[str] = []
        if bible:
            lines = [s for s in (collapse_ws(s) for s in bible.get_text("\n").split("\n")) if s]
        img = block.select_one(".recent-sermon-image img[src]")
        out.append(
            RawSermon(
                source_key=media_id,
                origin="scrape",
                title=clean_title(a.get_text()) or None,
                date=_parse_date(_txt(block.select_one(".recent-sermon-date")), "%d %B %Y"),
                speaker=_txt(block.select_one(".recent-sermon-speaker")),
                series_name=series,
                series_label_explicit=explicit,
                passage_text=lines[0] if lines else None,
                listed_references="; ".join(lines) if lines else None,
                audio_url=_https(_download_url(page_url, media_id, file_id)),
                image_url=_https(urljoin(page_url, img["src"])) if img else None,
                series_url=_https(page_url),
                source_url=_https(page_url),  # the series page this sermon is listed (and playable) on
            )
        )
    return out


def _txt(el: Tag | None) -> str | None:
    if el is None:
        return None
    t = collapse_ws(el.get_text(" "))
    return t or None


def _parse_date(text: str | None, fmt: str) -> date | None:
    if not text:
        return None
    try:
        return datetime.strptime(text.strip(), fmt).date()
    except ValueError:
        return None
