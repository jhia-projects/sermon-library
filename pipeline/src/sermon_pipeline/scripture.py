"""Parse printed scripture references ("1 Thessalonians 4:15 – 5:11") into schema passages."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# Canonical list shared with the schema and app: ../../schema/books.json
BOOKS_PATH = Path(__file__).resolve().parents[3] / "schema" / "books.json"
BOOKS: list[dict] = json.loads(BOOKS_PATH.read_text(encoding="utf-8"))["books"]

BOOK_DISPLAY: dict[str, str] = {b["code"]: b["name"] for b in BOOKS}
_NAME_TO_CODE: dict[str, str] = {}
for _b in BOOKS:
    for _n in (_b["name"], *_b.get("aliases", ())):
        _NAME_TO_CODE[_n.casefold()] = _b["code"]

_DASH = r"\s*[-–—]\s*"
_REF_RE = re.compile(
    r"^(?P<book>(?:[123]\s*)?[A-Za-z][A-Za-z ]*?)\s+"
    r"(?P<c1>\d+)(?::(?P<v1>\d+)[ab]?)?"
    rf"(?:{_DASH}(?:(?P<c2>\d+):)?(?P<n2>\d+)[ab]?)?$"
)


@dataclass(frozen=True)
class Reference:
    book: str  # OSIS code
    start_chapter: int
    end_chapter: int
    start_verse: int | None = None
    end_verse: int | None = None
    display: str = ""

    @property
    def span(self) -> tuple[str, int, int | None, int, int | None]:
        return (self.book, self.start_chapter, self.start_verse, self.end_chapter, self.end_verse)

    def to_passage(self) -> dict[str, object]:
        p: dict[str, object] = {"book": self.book, "startChapter": self.start_chapter}
        if self.start_verse is not None:
            p["startVerse"] = self.start_verse
        p["endChapter"] = self.end_chapter
        if self.end_verse is not None:
            p["endVerse"] = self.end_verse
        p["display"] = self.display
        return p


def book_code(name: str) -> str | None:
    return _NAME_TO_CODE.get(re.sub(r"\s+", " ", name).strip().casefold())


def parse_references(*texts: str | None) -> list[Reference]:
    """Every parsable reference in the given texts (split on ';' and ','), de-duplicated, in order.

    Items without a book name ("Romans 1:1-7, 16" -> "16") are skipped, not guessed.
    """
    out: list[Reference] = []
    for text in texts:
        for item in re.split(r"[;,\n]", text or ""):
            ref = parse_reference(item)
            if ref and ref.span not in {r.span for r in out}:  # same range, different dash = duplicate
                out.append(ref)
    return out


def parse_reference(text: str | None) -> Reference | None:
    """Parse a single reference. Only the first of a comma/semicolon list is used."""
    if not text:
        return None
    first = re.split(r"[;,]", text.strip(), maxsplit=1)[0].strip()
    m = _REF_RE.match(first)
    if not m:
        return None
    code = book_code(m["book"])
    if code is None:
        return None
    c1 = int(m["c1"])
    v1 = int(m["v1"]) if m["v1"] else None
    n2 = int(m["n2"]) if m["n2"] else None
    c2 = int(m["c2"]) if m["c2"] else None

    if v1 is None:
        # "Daniel 7" or chapter range "Daniel 1–2" (a "c:v" end here is unusual; honour it).
        end_chapter = c2 if c2 is not None else (n2 if n2 is not None else c1)
        end_verse = n2 if c2 is not None else None
        start_verse = None
    else:
        start_verse = v1
        end_chapter = c2 if c2 is not None else c1
        end_verse = n2 if n2 is not None else v1
    if end_chapter < c1 or (end_chapter == c1 and start_verse and end_verse and end_verse < start_verse):
        return None

    # Normalise spacing around the dash, keep the source's dash style.
    display = re.sub(r"\s*([-–—])\s*", r"\1", re.sub(r"\s+", " ", first))
    return Reference(code, c1, end_chapter, start_verse, end_verse, display)
