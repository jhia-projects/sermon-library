"""Small text helpers shared by RSS readers, scrapers and the builder."""

from __future__ import annotations

import re
import unicodedata

from .scripture import parse_reference

_TRAILING_PAREN = re.compile(r"^(?P<title>.*?)\s*\((?P<ref>[^()]*)\)\s*$")


def collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def split_title_and_passage(raw: str) -> tuple[str, str | None]:
    """'No Favourites (7) (Acts 12:19–24)' -> ('No Favourites (7)', 'Acts 12:19–24').

    Only a trailing parenthesis that parses as scripture is treated as the passage.
    """
    raw = collapse_ws(raw)
    m = _TRAILING_PAREN.match(raw)
    if m and parse_reference(m["ref"]):
        return clean_title(m["title"]), collapse_ws(m["ref"])
    return clean_title(raw), None


def clean_title(t: str) -> str:
    t = collapse_ws(t)
    t = re.sub(r"\.mp3$", "", t, flags=re.IGNORECASE)  # upload artefact: "But I say to you.mp3"
    # Archive titles are often wrapped in quotes: "'Jesus did many mighty works'".
    for q_open, q_close in (("'", "'"), ('"', '"'), ("‘", "’"), ("“", "”")):
        if len(t) > 2 and t.startswith(q_open) and t.endswith(q_close):
            t = t[1:-1]
            break
    return t.strip()


def parse_series_label(desc: str | None) -> tuple[str | None, bool]:
    """Extract a series name from a description / summary line.

    Returns (name, explicit). explicit=True for 'Series: X' and 'X: subtitle' forms; a bare
    description returns (text, False) and is only trusted later if it matches an explicit name.
    """
    if not desc:
        return None, False
    d = collapse_ws(desc)
    if not d:
        return None, False
    m = re.match(r"^series\s*:\s*(.+)$", d, flags=re.IGNORECASE)
    if m:
        return _tidy_series(m[1]), True
    if ":" in d:
        head = d.split(":", 1)[0]
        if head.strip():
            return _tidy_series(head), True
    return _tidy_series(d), False


def _tidy_series(s: str) -> str:
    s = collapse_ws(s)
    return s.strip(" .'\"‘’“”…")


def series_key(name: str) -> str:
    """Grouping key: case-, accent- and punctuation-insensitive."""
    n = unicodedata.normalize("NFKD", name)
    n = "".join(ch for ch in n if not unicodedata.combining(ch))
    n = re.sub(r"[^a-z0-9]+", " ", n.casefold())
    return n.strip()


def slugify(s: str) -> str:
    return re.sub(r"-+", "-", series_key(s).replace(" ", "-")).strip("-")


def parse_duration(text: str | None) -> int | None:
    """'00:28:49' / '28:49' / '1729' -> seconds."""
    if not text:
        return None
    text = text.strip()
    if text.isdigit():
        return int(text) or None
    parts = text.split(":")
    if not all(p.isdigit() for p in parts) or not 2 <= len(parts) <= 3:
        return None
    secs = 0
    for p in parts:
        secs = secs * 60 + int(p)
    return secs or None


_YT_RE = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|live/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})")


def youtube_id(url: str | None) -> str | None:
    if not url:
        return None
    m = _YT_RE.search(url)
    return m[1] if m else None
