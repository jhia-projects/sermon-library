"""Podcast RSS 2.0 (+ iTunes namespace) reader -> RawSermon(origin="rss").

One reader, a per-church item parser chosen by `[rss].format` in the source toml (FEED_FORMATS).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from email.utils import parsedate_to_datetime

from .models import RawSermon
from .normalize import clean_title, collapse_ws, parse_duration, parse_series_label, split_title_and_passage, youtube_id
from .scripture import parse_reference

ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


class FeedError(Exception):
    pass


def parse_feed(xml_text: str, fmt: str = "generic") -> list[RawSermon]:
    parse_item = FEED_FORMATS[fmt]
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError as e:
        raise FeedError(f"unparsable RSS: {e}") from e
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise FeedError(f"not an RSS 2.0 document (root <{root.tag}>)")
    return [s for item in channel.findall("item") if (s := parse_item(item)) is not None]


def _text(el: ET.Element, tag: str) -> str | None:
    child = el.find(tag)
    if child is None or child.text is None:
        return None
    t = collapse_ws(child.text)
    return t or None


def _item(item: ET.Element) -> RawSermon | None:
    guid = _text(item, "guid")
    link = _text(item, "link")
    key = _source_key(guid, link)
    if key is None:
        return None

    raw_title = _text(item, "title") or ""
    title, passage = split_title_and_passage(raw_title)

    desc = _text(item, "description") or _text(item, f"{ITUNES}summary")
    series, explicit = parse_series_label(desc)

    date = None
    if pub := _text(item, "pubDate"):
        try:
            date = parsedate_to_datetime(pub).date()
        except (TypeError, ValueError):
            date = None

    audio = video = None
    enc = item.find("enclosure")
    if enc is not None and (url := enc.get("url", "")).startswith("https://"):
        mime = (enc.get("type") or "").lower()
        if mime.startswith("video/"):
            video = url
        else:
            audio = url

    image = None
    img = item.find(f"{ITUNES}image")
    if img is not None:
        image = img.get("href") or (img.text or "").strip() or None
    if image is None:
        image = _text(item, "image/url")

    return RawSermon(
        source_key=key,
        origin="rss",
        title=clean_title(title) or None,
        date=date,
        speaker=_text(item, f"{ITUNES}author"),
        series_name=series,
        series_label_explicit=explicit,
        passage_text=passage,
        audio_url=audio,
        video_url=video,
        youtube_id=youtube_id(link),
        duration_seconds=parse_duration(_text(item, f"{ITUNES}duration")),
        image_url=image if image and image.startswith("https://") else None,
        source_url=link if link and link.startswith("https://") else None,
    )


def _source_key(guid: str | None, link: str | None) -> str | None:
    # Hubb (All Souls) guids look like "m_371615"; the same media_id appears in site URLs.
    for candidate in (guid, link):
        if candidate and (m := re.search(r"(?:^m_|media_id=)(\d+)", candidate)):
            return m[1]
    return guid or link


# --- St Helen's Bishopsgate ------------------------------------------------------------------
# https://api.st-helens.org.uk/v1.0/feeds/{sunday,midweek}.xml. Each item prints:
#   <itunes:subtitle>Psalm 110:1-3 - George Diwakar (6pm)</itunes:subtitle>   (midweek: no "(time)")
#   <itunes:author>George Diwakar</itunes:author>
#   <enclosure url=".../podcast-download/59582/SE26-047.mp3"/>   59582 = /resources/talk/59582/ id
#   <description>George Diwakar - At Christmas we sing...</description>   (a blurb, not a series)
# There is no series and no <link>: series and page URL come from the talk pages (backfill).

_SH_ENCLOSURE = re.compile(r"^https://api\.st-helens\.org\.uk/v1\.0/downloads/podcast-download/(\d+)/[^/]+$")


def _sthelens_item(item: ET.Element) -> RawSermon | None:
    enc = item.find("enclosure")
    url = enc.get("url", "") if enc is not None else ""
    m = _SH_ENCLOSURE.match(url)
    if m is None:
        return None  # without the talk id we can't match it to its page; skip rather than guess
    speaker = _text(item, f"{ITUNES}author")
    passage = service = None
    if subtitle := _text(item, f"{ITUNES}subtitle"):
        if t := re.search(r"\(([^()]*\d[^()]*(?:am|pm))\)\s*$", subtitle):
            service = t[1].strip()
        head = subtitle.split(" - ", 1)[0].strip()
        # Only a printed reference counts (rule 5); a subtitle without one gives no passage.
        if " - " in subtitle and parse_reference(head):
            passage = head
    date = None
    if pub := _text(item, "pubDate"):
        try:
            date = parsedate_to_datetime(pub).date()
        except (TypeError, ValueError):
            date = None
    return RawSermon(
        source_key=m[1],
        origin="rss",
        title=clean_title(_text(item, "title") or "") or None,
        date=date,
        speaker=speaker,
        passage_text=passage,
        listed_references=passage,
        audio_url=url,
        duration_seconds=parse_duration(_text(item, f"{ITUNES}duration")),
        service_time=service,
    )


FEED_FORMATS: dict[str, Callable[[ET.Element], RawSermon | None]] = {
    "generic": _item,
    "sthelens": _sthelens_item,
}
