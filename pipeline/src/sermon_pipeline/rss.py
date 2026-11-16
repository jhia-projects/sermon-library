"""Generic podcast RSS 2.0 (+ iTunes namespace) reader -> RawSermon(origin="rss")."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from .models import RawSermon
from .normalize import clean_title, collapse_ws, parse_duration, parse_series_label, split_title_and_passage, youtube_id

ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


class FeedError(Exception):
    pass


def parse_feed(xml_text: str) -> list[RawSermon]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError as e:
        raise FeedError(f"unparsable RSS: {e}") from e
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise FeedError(f"not an RSS 2.0 document (root <{root.tag}>)")
    return [s for item in channel.findall("item") if (s := _item(item)) is not None]


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
